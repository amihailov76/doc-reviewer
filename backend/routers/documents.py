"""
Эндпойнты для работы с документами:
- POST /api/documents/upload          — загрузка файла
- GET  /api/documents/                — список документов
- GET  /api/documents/{id}/structure  — дерево разделов
- PATCH /api/documents/{id}/type      — смена типа документа
- DELETE /api/documents/{id}          — удаление документа
"""

import os
import shutil
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db, Document, Instruction, Evaluation
from backend.services.parser import parse_document
from backend.services.detector import classify_section
from backend.services.glossary import extract_glossary
from backend.services.differ import match_sections

router = APIRouter(prefix="/api/documents", tags=["documents"])

# Папка для хранения загруженных файлов
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UPLOAD_DIR = os.path.join(BASE_DIR, "data", "uploads")

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".md", ".txt"}

DOC_TYPES = [
    "Руководство по развёртыванию",
    "Руководство пользователя",
    "Руководство администратора",
    "Справочник по настройке источников",
    "Справочник по PDQL",
]


class SetDocTypeRequest(BaseModel):
    doc_type: str


@router.post("/upload")
def upload_document(
    file: UploadFile = File(...),
    project_id: int = None,
    db: Session = Depends(get_db),
):
    """
    Загружает документ и парсит его структуру.
    Если файл с таким именем уже существует — возвращает конфликт,
    чтобы фронтенд мог показать диалог подтверждения.
    """
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # Проверяем расширение
    _, ext = os.path.splitext(file.filename)
    if ext.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Неподдерживаемый формат. Разрешены: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Проверяем, не загружен ли уже файл с таким именем
    existing = db.query(Document).filter(Document.filename == file.filename).first()
    if existing:
        return {
            "conflict": True,
            "existing_id": existing.id,
            "filename": file.filename,
        }

    return _save_and_parse(file, db, project_id=project_id)


@router.post("/upload/replace/{document_id}")
def replace_document(
    document_id: int,
    file: UploadFile = File(...),
    project_id: int = None,
    db: Session = Depends(get_db),
):
    """
    Заменяет существующий документ новым файлом (после подтверждения пользователем).
    Сохраняет оценки неизменившихся разделов через difflib-сравнение.
    """
    existing = db.query(Document).filter(Document.id == document_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Документ не найден")

    effective_project_id = project_id if project_id is not None else existing.project_id

    # Снимаем снимок старых инструкций с оценками до удаления документа
    old_instructions = (
        db.query(Instruction)
        .filter(Instruction.document_id == document_id)
        .all()
    )

    # Удаляем старый файл с диска
    if os.path.exists(existing.file_path):
        os.remove(existing.file_path)

    # Удаляем старый документ (каскадно удалятся instructions и evaluations)
    db.delete(existing)
    db.commit()

    # Парсим новый файл и записываем в БД
    result = _save_and_parse(file, db, project_id=effective_project_id)

    # Применяем diff-сопоставление: переносим оценки и проставляем подсказки
    if old_instructions and not result.get("conflict"):
        _apply_diff_matches(result["id"], old_instructions, db)
        result["diff_applied"] = True

    return result


def _apply_diff_matches(new_doc_id: int, old_instructions: list, db) -> None:
    """
    Сопоставляет разделы новой версии документа со старыми.
    - Для неизменившихся разделов копирует оценку (без LLM-вызова).
    - Для частично изменившихся записывает diff_hint в Instruction.
    """
    import logging
    log = logging.getLogger(__name__)

    new_instructions = (
        db.query(Instruction)
        .filter(Instruction.document_id == new_doc_id)
        .order_by(Instruction.id)
        .all()
    )

    matches = match_sections(old_instructions, new_instructions)

    copied = 0
    hinted = 0

    for match, new_instr in zip(matches, new_instructions):
        if match.action == "copy" and match.old_evaluation:
            ev = match.old_evaluation
            evaluation = Evaluation(
                instruction_id=new_instr.id,
                color=ev["color"],
                criteria_results=ev["criteria_results"],
                recommendations=ev["recommendations"],
                model_used=ev["model_used"],
                overrides=ev["overrides"],
            )
            db.add(evaluation)
            copied += 1

        elif match.action == "hint" and match.diff_hint:
            new_instr.diff_hint = match.diff_hint
            hinted += 1

    db.commit()
    log.info(
        f"Diff-сопоставление doc_id={new_doc_id}: "
        f"скопировано оценок={copied}, подсказок={hinted}, "
        f"новых разделов={sum(1 for m in matches if m.action == 'fresh')}"
    )


def _save_and_parse(file: UploadFile, db: Session, project_id: int = None) -> dict:
    """Сохраняет файл на диск, парсит структуру, записывает в БД."""
    _, ext = os.path.splitext(file.filename)
    file_path = os.path.join(UPLOAD_DIR, file.filename)

    # Сохраняем файл
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Парсим структуру
    try:
        result = parse_document(file_path)
    except Exception as e:
        os.remove(file_path)
        raise HTTPException(status_code=422, detail=f"Ошибка парсинга: {str(e)}")

    # Записываем документ в БД
    doc = Document(
        filename=file.filename,
        file_type=ext.lstrip(".").lower(),
        file_path=file_path,
        project_id=project_id,
    )
    db.add(doc)
    db.flush()  # получаем doc.id до commit

    # Записываем разделы как инструкции, сразу запускаем классификацию
    for i, section in enumerate(result.sections):
        detection = classify_section(section.title, section.content or "")
        instruction = Instruction(
            document_id=doc.id,
            title=section.title,
            content=section.content,
            classification=detection.classification,
            page_number=section.page_number,
            section_path=_build_section_path(result.sections, i),
        )
        db.add(instruction)

    # Извлекаем глоссарий продукта из всех разделов через YAKE
    try:
        doc.glossary = extract_glossary(result.sections)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Не удалось извлечь глоссарий: {e}")
        doc.glossary = []

    db.commit()
    db.refresh(doc)

    # Считаем статистику классификации для ответа
    counts = {"instruction": 0, "possible": 0, "non-instruction": 0}
    for instr in db.query(Instruction).filter(Instruction.document_id == doc.id).all():
        counts[instr.classification] = counts.get(instr.classification, 0) + 1

    return {
        "conflict": False,
        "id": doc.id,
        "filename": doc.filename,
        "file_type": doc.file_type,
        "sections_count": len(result.sections),
        "classification": counts,
    }


def _build_section_path(sections: list, index: int) -> str:
    """
    Строит путь раздела в дереве вида «1 > 1.2 > 1.2.3».
    Проходим назад по списку и собираем цепочку родителей.
    """
    target = sections[index]
    path_parts = [target.title[:40]]
    current_level = target.level

    for j in range(index - 1, -1, -1):
        if sections[j].level < current_level:
            path_parts.insert(0, sections[j].title[:40])
            current_level = sections[j].level
        if current_level <= 1:
            break

    return " > ".join(path_parts)


@router.get("/")
def list_documents(db: Session = Depends(get_db)):
    """Список всех загруженных документов."""
    docs = db.query(Document).order_by(Document.uploaded_at.desc()).all()
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "file_type": d.file_type,
            "doc_type": d.doc_type,
            "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
            "last_evaluated_at": d.last_evaluated_at.isoformat() if d.last_evaluated_at else None,
        }
        for d in docs
    ]


@router.get("/{document_id}/structure")
def get_structure(document_id: int, db: Session = Depends(get_db)):
    """
    Возвращает дерево разделов документа.
    Разделы вложены по уровню: children содержат разделы с level > текущего.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")

    instructions = (
        db.query(Instruction)
        .filter(Instruction.document_id == document_id)
        .order_by(Instruction.id)
        .all()
    )

    # Строим плоский список, вложенность отдаём фронтенду
    flat = [
        {
            "id": instr.id,
            "title": instr.title,
            "content": instr.content,
            "level": _level_from_path(instr.section_path),
            "page_number": instr.page_number,
            "section_path": instr.section_path,
            "classification": instr.classification,
            "include_in_evaluation": bool(instr.include_in_evaluation),
            "has_evaluation": instr.evaluation is not None,
            "color": instr.evaluation.color if instr.evaluation else None,
            "criteria_results": instr.evaluation.criteria_results if instr.evaluation else None,
            "recommendations": instr.evaluation.recommendations if instr.evaluation else None,
            "overrides": instr.evaluation.overrides or {} if instr.evaluation else {},
        }
        for instr in instructions
    ]

    return {
        "document": {
            "id": doc.id,
            "filename": doc.filename,
            "file_type": doc.file_type,
            "doc_type": doc.doc_type,
            "doc_types": DOC_TYPES,
            "project_id": doc.project_id,
        },
        "sections": flat,
    }


def _level_from_path(section_path: str) -> int:
    """Определяет уровень вложенности по section_path (количество разделителей > )."""
    if not section_path:
        return 1
    return section_path.count(" > ") + 1


@router.patch("/{document_id}/type")
def set_doc_type(
    document_id: int,
    body: SetDocTypeRequest,
    db: Session = Depends(get_db),
):
    """Устанавливает тип документа."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")
    if body.doc_type not in DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"Неизвестный тип документа: {body.doc_type}")
    doc.doc_type = body.doc_type
    db.commit()
    return {"ok": True, "doc_type": doc.doc_type}


@router.delete("/{document_id}")
def delete_document(document_id: int, db: Session = Depends(get_db)):
    """Удаляет документ и все связанные данные."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")
    if os.path.exists(doc.file_path):
        os.remove(doc.file_path)
    db.delete(doc)
    db.commit()
    return {"ok": True}


@router.post("/{document_id}/reclassify")
def reclassify_document(document_id: int, db: Session = Depends(get_db)):
    """
    Повторно классифицирует все разделы документа без перезагрузки файла.
    Полезно после обновления логики детектора.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")

    instructions = db.query(Instruction).filter(Instruction.document_id == document_id).all()
    counts = {"instruction": 0, "possible": 0, "non-instruction": 0}

    for instr in instructions:
        detection = classify_section(instr.title, instr.content or "")
        instr.classification = detection.classification
        counts[detection.classification] = counts.get(detection.classification, 0) + 1

    db.commit()
    return {"ok": True, "classification": counts}

"""
Эндпойнты для работы с проектами:
- GET    /api/projects/                        — список проектов
- POST   /api/projects/                        — создать проект
- GET    /api/projects/{id}                    — проект со списком документов
- PATCH  /api/projects/{id}                    — переименовать / обновить контекст
- DELETE /api/projects/{id}                    — удалить проект
- POST   /api/projects/{id}/generate-context   — сгенерировать контекст через LLM
- PATCH  /api/documents/{id}/project           — переместить документ в проект
"""

from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from backend.database import get_db, Project, Document, Instruction

router = APIRouter(prefix="/api/projects", tags=["projects"])


# ── Схемы запросов ─────────────────────────────────────────────────────────────

class CreateProjectRequest(BaseModel):
    name: str


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    product_context: Optional[str] = None


class SetDocumentProjectRequest(BaseModel):
    project_id: Optional[int] = None  # None = убрать из проекта


# ── CRUD ───────────────────────────────────────────────────────────────────────

@router.get("/")
def list_projects(db: Session = Depends(get_db)):
    """Возвращает список всех проектов со статистикой."""
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    return [_serialize_project(p, db) for p in projects]


@router.post("/")
def create_project(body: CreateProjectRequest, db: Session = Depends(get_db)):
    """Создаёт новый проект."""
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Название проекта не может быть пустым")
    project = Project(name=name)
    db.add(project)
    db.commit()
    db.refresh(project)
    return _serialize_project(project, db)


@router.get("/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db)):
    """Возвращает проект со списком документов и их статусом оценки."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден")
    return _serialize_project_detail(project, db)


@router.patch("/{project_id}")
def update_project(project_id: int, body: UpdateProjectRequest, db: Session = Depends(get_db)):
    """Переименовывает проект или обновляет контекст продукта."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден")

    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Название не может быть пустым")
        project.name = name

    if body.product_context is not None:
        project.product_context = body.product_context
        # Ручное редактирование не обновляет context_generated_at

    db.commit()
    db.refresh(project)
    return _serialize_project(project, db)


@router.delete("/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    """
    Удаляет проект. Документы не удаляются — project_id становится NULL,
    они остаются в системе без привязки к проекту.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден")

    # Отвязываем документы, не удаляем
    db.query(Document).filter(Document.project_id == project_id).update(
        {Document.project_id: None}, synchronize_session=False
    )
    db.delete(project)
    db.commit()
    return {"ok": True}


# ── Генерация контекста ────────────────────────────────────────────────────────

@router.post("/{project_id}/generate-context")
def generate_context(project_id: int, db: Session = Depends(get_db)):
    """
    Генерирует контекст продукта через LLM из non-instruction разделов
    документов проекта. Результат сохраняется в project.product_context.
    """
    from backend.services.context_generator import generate_project_context, ContextGenerationError

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден")

    docs = db.query(Document).filter(Document.project_id == project_id).all()
    if not docs:
        raise HTTPException(status_code=400, detail="В проекте нет документов")

    # Собираем non-instruction разделы из всех документов проекта
    non_instr_sections = (
        db.query(Instruction)
        .filter(
            Instruction.document_id.in_([d.id for d in docs]),
            Instruction.classification == "non-instruction",
            Instruction.content != None,
            Instruction.content != "",
        )
        .order_by(Instruction.document_id, Instruction.id)
        .limit(60)  # не больше 60 разделов, чтобы не перегружать контекст
        .all()
    )

    if not non_instr_sections:
        raise HTTPException(
            status_code=400,
            detail="Не найдено вводных разделов для генерации контекста. "
                   "Убедитесь, что документы загружены и проанализированы."
        )

    try:
        context_text = generate_project_context(non_instr_sections)
    except ContextGenerationError as e:
        raise HTTPException(status_code=502, detail={"message": e.message, "advice": e.advice})

    project.product_context = context_text
    project.context_generated_at = datetime.utcnow()
    db.commit()

    return {
        "ok": True,
        "product_context": context_text,
        "context_generated_at": project.context_generated_at.isoformat(),
    }


# ── Управление документами проекта ────────────────────────────────────────────

@router.patch("/documents/{document_id}/assign")
def assign_document(
    document_id: int,
    body: SetDocumentProjectRequest,
    db: Session = Depends(get_db),
):
    """Перемещает документ в указанный проект (или отвязывает, если project_id=null)."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")

    if body.project_id is not None:
        project = db.query(Project).filter(Project.id == body.project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Проект не найден")

    doc.project_id = body.project_id
    db.commit()
    return {"ok": True, "document_id": document_id, "project_id": body.project_id}


# ── Сериализация ───────────────────────────────────────────────────────────────

def _serialize_project(project: Project, db: Session) -> dict:
    """Краткое представление проекта для списка."""
    doc_count = db.query(Document).filter(Document.project_id == project.id).count()
    return {
        "id": project.id,
        "name": project.name,
        "has_context": bool(project.product_context),
        "context_generated_at": project.context_generated_at.isoformat() if project.context_generated_at else None,
        "doc_count": doc_count,
        "created_at": project.created_at.isoformat() if project.created_at else None,
    }


def _serialize_project_detail(project: Project, db: Session) -> dict:
    """Полное представление проекта с документами."""
    docs = db.query(Document).filter(Document.project_id == project.id).order_by(Document.uploaded_at.desc()).all()
    return {
        "id": project.id,
        "name": project.name,
        "product_context": project.product_context,
        "has_context": bool(project.product_context),
        "context_generated_at": project.context_generated_at.isoformat() if project.context_generated_at else None,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "documents": [_serialize_doc(d, db) for d in docs],
    }


def _serialize_doc(doc: Document, db: Session) -> dict:
    """Документ с краткой статистикой оценки."""
    from backend.database import Evaluation
    total = db.query(Instruction).filter(
        Instruction.document_id == doc.id,
        Instruction.classification.in_(["instruction", "possible"]),
        Instruction.include_in_evaluation == 1,
    ).count()
    evaluated = db.query(Evaluation).join(Instruction).filter(
        Instruction.document_id == doc.id
    ).count()
    return {
        "id": doc.id,
        "filename": doc.filename,
        "file_type": doc.file_type,
        "doc_type": doc.doc_type,
        "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
        "last_evaluated_at": doc.last_evaluated_at.isoformat() if doc.last_evaluated_at else None,
        "total_instructions": total,
        "evaluated_count": evaluated,
    }

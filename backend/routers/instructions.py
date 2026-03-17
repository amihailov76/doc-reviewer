"""
Эндпойнты для работы с отдельными инструкциями:
- GET   /api/instructions/{id}                    — данные одной инструкции
- PATCH /api/instructions/{id}/include            — включить/исключить из оценки
- PATCH /api/instructions/{id}/override           — пометить ложное срабатывание
- PATCH /api/instructions/document/{id}/include-all — массовое включение/исключение
- GET   /api/instructions/possible                — список разделов с классификацией "possible"
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, Literal

from backend.database import get_db, Instruction, Evaluation

router = APIRouter(prefix="/api/instructions", tags=["instructions"])


class SetIncludeRequest(BaseModel):
    include: bool


class BulkIncludeRequest(BaseModel):
    include: bool
    classification: Optional[str] = None


class OverrideRequest(BaseModel):
    type: Literal["criteria", "section"]
    criterion: Optional[str] = None  # для type="criteria"
    value: bool                       # True = помечено как ложное срабатывание


@router.get("/possible")
def get_possible(db: Session = Depends(get_db)):
    """Возвращает все разделы с классификацией 'possible' для ручного просмотра."""
    instructions = (
        db.query(Instruction)
        .filter(Instruction.classification == "possible")
        .order_by(Instruction.document_id, Instruction.id)
        .all()
    )
    return [_serialize(i) for i in instructions]


@router.patch("/document/{document_id}/include-all")
def bulk_include(
    document_id: int,
    body: BulkIncludeRequest,
    db: Session = Depends(get_db),
):
    q = db.query(Instruction).filter(Instruction.document_id == document_id)
    if body.classification:
        q = q.filter(Instruction.classification == body.classification)
    updated = q.update(
        {"include_in_evaluation": 1 if body.include else 0},
        synchronize_session=False,
    )
    db.commit()
    return {"ok": True, "updated": updated, "include": body.include}


@router.get("/{instruction_id}")
def get_instruction(instruction_id: int, db: Session = Depends(get_db)):
    instr = db.query(Instruction).filter(Instruction.id == instruction_id).first()
    if not instr:
        raise HTTPException(status_code=404, detail="Инструкция не найдена")
    return _serialize(instr)


@router.patch("/{instruction_id}/include")
def set_include(
    instruction_id: int,
    body: SetIncludeRequest,
    db: Session = Depends(get_db),
):
    instr = db.query(Instruction).filter(Instruction.id == instruction_id).first()
    if not instr:
        raise HTTPException(status_code=404, detail="Инструкция не найдена")
    instr.include_in_evaluation = 1 if body.include else 0
    db.commit()
    return {"ok": True, "include_in_evaluation": body.include}


@router.patch("/{instruction_id}/override")
def set_override(
    instruction_id: int,
    body: OverrideRequest,
    db: Session = Depends(get_db),
):
    """
    Помечает или снимает отметку ложного срабатывания.
    Отметки сохраняются при повторной оценке.
    """
    instr = db.query(Instruction).filter(Instruction.id == instruction_id).first()
    if not instr:
        raise HTTPException(status_code=404, detail="Инструкция не найдена")
    if not instr.evaluation:
        raise HTTPException(status_code=400, detail="Раздел ещё не оценён")

    ev = instr.evaluation
    overrides = dict(ev.overrides or {})

    if body.type == "section":
        overrides["section"] = body.value
    elif body.type == "criteria":
        if not body.criterion:
            raise HTTPException(status_code=400, detail="Укажите criterion для type=criteria")
        criteria_overrides = dict(overrides.get("criteria", {}))
        if body.value:
            criteria_overrides[body.criterion] = True
        else:
            criteria_overrides.pop(body.criterion, None)
        overrides["criteria"] = criteria_overrides

    ev.overrides = overrides
    db.commit()
    return {"ok": True, "overrides": overrides}


def _serialize(instr: Instruction) -> dict:
    ev = instr.evaluation
    return {
        "id": instr.id,
        "document_id": instr.document_id,
        "title": instr.title,
        "content": instr.content,
        "classification": instr.classification,
        "page_number": instr.page_number,
        "section_path": instr.section_path,
        "include_in_evaluation": bool(instr.include_in_evaluation),
        "color": ev.color if ev else None,
        "overrides": ev.overrides or {} if ev else {},
    }


class SetIncludeRequest(BaseModel):
    include: bool


class BulkIncludeRequest(BaseModel):
    include: bool
    classification: Optional[str] = None  # если указан — фильтр по классификации


@router.get("/possible")
def get_possible(db: Session = Depends(get_db)):
    """Возвращает все разделы с классификацией 'possible' для ручного просмотра."""
    instructions = (
        db.query(Instruction)
        .filter(Instruction.classification == "possible")
        .order_by(Instruction.document_id, Instruction.id)
        .all()
    )
    return [_serialize(i) for i in instructions]


@router.patch("/document/{document_id}/include-all")
def bulk_include(
    document_id: int,
    body: BulkIncludeRequest,
    db: Session = Depends(get_db),
):
    """
    Массово включает или исключает разделы документа из оценки.
    Если передан classification — применяется только к разделам с этой классификацией.
    """
    q = db.query(Instruction).filter(Instruction.document_id == document_id)
    if body.classification:
        q = q.filter(Instruction.classification == body.classification)

    updated = q.update(
        {"include_in_evaluation": 1 if body.include else 0},
        synchronize_session=False,
    )
    db.commit()
    return {"ok": True, "updated": updated, "include": body.include}


@router.get("/{instruction_id}")
def get_instruction(instruction_id: int, db: Session = Depends(get_db)):
    """Возвращает полные данные одной инструкции."""
    instr = db.query(Instruction).filter(Instruction.id == instruction_id).first()
    if not instr:
        raise HTTPException(status_code=404, detail="Инструкция не найдена")
    return _serialize(instr)


@router.patch("/{instruction_id}/include")
def set_include(
    instruction_id: int,
    body: SetIncludeRequest,
    db: Session = Depends(get_db),
):
    """Включает или исключает раздел из оценки."""
    instr = db.query(Instruction).filter(Instruction.id == instruction_id).first()
    if not instr:
        raise HTTPException(status_code=404, detail="Инструкция не найдена")
    instr.include_in_evaluation = 1 if body.include else 0
    db.commit()
    return {"ok": True, "include_in_evaluation": body.include}


def _serialize(instr: Instruction) -> dict:
    return {
        "id": instr.id,
        "document_id": instr.document_id,
        "title": instr.title,
        "content": instr.content,
        "classification": instr.classification,
        "page_number": instr.page_number,
        "section_path": instr.section_path,
        "include_in_evaluation": bool(instr.include_in_evaluation),
        "color": instr.evaluation.color if instr.evaluation else None,
    }

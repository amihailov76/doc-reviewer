from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from backend.config import get_active_model, set_active_model
from backend.database import get_db, Model, CriteriaSet, get_active_criteria_content, _find_criteria_file
import os
import re

router = APIRouter(prefix="/api/config", tags=["config"])


# ── Вспомогательные функции ───────────────────────────────────────────────────

def _parse_criteria_content(content: str) -> dict[str, str]:
    """Парсит Markdown критериев и возвращает словарь {id: описание}."""
    result = {}
    pattern = re.compile(r"###\s+(\d+[\.\d]*)\s+(.+?)\n(.+?)(?=\n##|\n###|\Z)", re.DOTALL)
    for match in pattern.finditer(content):
        crit_id = match.group(1).strip()
        name = match.group(2).strip()
        description = match.group(3).strip().split("\n")[0]
        result[crit_id] = f"{name} — {description}"
    return result


def _model_to_dict(m: Model) -> dict:
    return {
        "id": m.id,
        "model_id": m.model_id,
        "name": m.name,
        "provider": m.provider,
        "base_url": m.base_url,
        "requires_key": m.requires_key,
        "has_key": bool(m.api_key),
        "is_active": m.is_active,
    }


def _criteria_to_dict(c: CriteriaSet) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "content": c.content,
        "is_active": c.is_active,
        "is_default": c.is_default,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


# ── Pydantic-схемы ────────────────────────────────────────────────────────────

class SetActiveModelRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    model_id: str


class ModelCreateRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    model_id: str
    name: str
    provider: str
    base_url: str
    requires_key: bool = True
    api_key: Optional[str] = None


class ModelUpdateRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    name: str
    provider: str
    base_url: str
    requires_key: bool
    api_key: Optional[str] = None


class CriteriaCreateRequest(BaseModel):
    name: str
    content: str


class CriteriaUpdateRequest(BaseModel):
    name: str
    content: str


# ── Модели ────────────────────────────────────────────────────────────────────

@router.get("/models")
def get_models(db: Session = Depends(get_db)):
    models = db.query(Model).order_by(Model.id).all()
    active = next((m for m in models if m.is_active), models[0] if models else None)
    return {
        "models": [_model_to_dict(m) for m in models],
        "active_model": active.model_id if active else "",
    }


@router.post("/models")
def create_model(body: ModelCreateRequest, db: Session = Depends(get_db)):
    existing = db.query(Model).filter(Model.model_id == body.model_id).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Модель с ID '{body.model_id}' уже существует")
    m = Model(
        model_id=body.model_id,
        name=body.name,
        provider=body.provider,
        base_url=body.base_url,
        requires_key=body.requires_key,
        api_key=body.api_key.strip() if body.api_key else None,
        is_active=False,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return _model_to_dict(m)


@router.put("/models/{model_id}")
def update_model(model_id: int, body: ModelUpdateRequest, db: Session = Depends(get_db)):
    m = db.query(Model).filter(Model.id == model_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Модель не найдена")
    m.name = body.name
    m.provider = body.provider
    m.base_url = body.base_url
    m.requires_key = body.requires_key
    if body.api_key is not None:
        m.api_key = body.api_key.strip() or None
    db.commit()
    db.refresh(m)
    return _model_to_dict(m)


@router.delete("/models/{model_id}")
def delete_model(model_id: int, db: Session = Depends(get_db)):
    m = db.query(Model).filter(Model.id == model_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Модель не найдена")
    if m.is_active:
        other = db.query(Model).filter(Model.id != model_id).first()
        if other:
            other.is_active = True
    db.delete(m)
    db.commit()
    return {"ok": True}


@router.get("/active-model")
def get_active():
    model = get_active_model()
    if not model:
        raise HTTPException(status_code=404, detail="Активная модель не найдена")
    return model.dict()


@router.patch("/active-model")
def update_active_model(body: SetActiveModelRequest):
    success = set_active_model(body.model_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Модель '{body.model_id}' не найдена")
    return {"ok": True, "active_model": body.model_id}


# ── Наборы критериев ──────────────────────────────────────────────────────────

@router.get("/criteria-sets")
def list_criteria_sets(db: Session = Depends(get_db)):
    """Возвращает список всех наборов критериев."""
    sets = db.query(CriteriaSet).order_by(CriteriaSet.id).all()
    return [_criteria_to_dict(c) for c in sets]


@router.post("/criteria-sets")
def create_criteria_set(body: CriteriaCreateRequest, db: Session = Depends(get_db)):
    """Создаёт новый набор критериев."""
    c = CriteriaSet(name=body.name, content=body.content, is_active=False, is_default=False)
    db.add(c)
    db.commit()
    db.refresh(c)
    return _criteria_to_dict(c)


@router.put("/criteria-sets/{set_id}")
def update_criteria_set(set_id: int, body: CriteriaUpdateRequest, db: Session = Depends(get_db)):
    """Обновляет название и контент набора критериев."""
    c = db.query(CriteriaSet).filter(CriteriaSet.id == set_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Набор критериев не найден")
    c.name = body.name
    c.content = body.content
    db.commit()
    db.refresh(c)
    return _criteria_to_dict(c)


@router.patch("/criteria-sets/{set_id}/activate")
def activate_criteria_set(set_id: int, db: Session = Depends(get_db)):
    """Устанавливает набор критериев как активный."""
    c = db.query(CriteriaSet).filter(CriteriaSet.id == set_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Набор критериев не найден")
    db.query(CriteriaSet).update({CriteriaSet.is_active: False})
    c.is_active = True
    db.commit()
    return _criteria_to_dict(c)


@router.patch("/criteria-sets/{set_id}/reset")
def reset_criteria_set(set_id: int, db: Session = Depends(get_db)):
    """Сбрасывает дефолтный набор к исходному содержимому из criteria.md."""
    c = db.query(CriteriaSet).filter(CriteriaSet.id == set_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Набор критериев не найден")
    if not c.is_default:
        raise HTTPException(status_code=400, detail="Сброс доступен только для дефолтного набора")
    path = _find_criteria_file()
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Файл criteria.md не найден")
    with open(path, "r", encoding="utf-8") as f:
        c.content = f.read()
    db.commit()
    db.refresh(c)
    return _criteria_to_dict(c)


@router.delete("/criteria-sets/{set_id}")
def delete_criteria_set(set_id: int, db: Session = Depends(get_db)):
    """Удаляет набор критериев. Дефолтный набор удалить нельзя."""
    c = db.query(CriteriaSet).filter(CriteriaSet.id == set_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Набор критериев не найден")
    if c.is_default:
        raise HTTPException(status_code=400, detail="Дефолтный набор критериев удалить нельзя")
    if c.is_active:
        # Активируем дефолтный или первый из оставшихся
        fallback = db.query(CriteriaSet).filter(CriteriaSet.id != set_id).first()
        if fallback:
            fallback.is_active = True
    db.delete(c)
    db.commit()
    return {"ok": True}


# ── Критерии (словарь для тултипов) ──────────────────────────────────────────

@router.get("/criteria")
def get_criteria():
    """Возвращает словарь {id: описание} активного набора критериев."""
    content = get_active_criteria_content()
    if not content:
        raise HTTPException(status_code=404, detail="Активный набор критериев не найден")
    result = _parse_criteria_content(content)
    if not result:
        raise HTTPException(status_code=404, detail="Критерии не найдены в активном наборе")
    return result

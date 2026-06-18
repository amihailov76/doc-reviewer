from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from backend.config import load_config, get_active_model, set_active_model
from backend.database import get_db, Model
import os
import re
import sys

router = APIRouter(prefix="/api/config", tags=["config"])

if getattr(sys, "frozen", False):
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CRITERIA_PATH = os.path.join(_BASE_DIR, "criteria.md")


def _parse_criteria(path: str) -> dict[str, str]:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        content = f.read()
    result = {}
    pattern = re.compile(r"###\s+(\d+\.\d+)\s+(.+?)\n(.+?)(?=\n##|\n###|\Z)", re.DOTALL)
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
        "has_key": bool(m.api_key),   # есть ли ключ — но сам ключ не отдаём
        "is_active": m.is_active,
    }


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
    api_key: Optional[str] = None   # None = не менять, "" = удалить


# ── Модели ───────────────────────────────────────────────────────────────────

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
        # Пустая строка = удалить ключ, непустая = сохранить
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


# ── Критерии ─────────────────────────────────────────────────────────────────

@router.get("/criteria")
def get_criteria():
    criteria = _parse_criteria(_CRITERIA_PATH)
    if not criteria:
        raise HTTPException(status_code=404, detail="criteria.md не найден или пуст")
    return criteria

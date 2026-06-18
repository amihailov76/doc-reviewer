import os
from typing import Optional
from pydantic import BaseModel


class ModelConfig(BaseModel):
    model_config = {"protected_namespaces": ()}
    id: str
    name: str
    provider: str
    base_url: str
    requires_key: bool = False
    api_key: Optional[str] = None

    def dict(self, **kwargs):
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "base_url": self.base_url,
            "requires_key": self.requires_key,
            # api_key намеренно не включён — не отдаём ключ на фронтенд
        }


def _db_model_to_config(m) -> ModelConfig:
    return ModelConfig(
        id=m.model_id,
        name=m.name,
        provider=m.provider,
        base_url=m.base_url,
        requires_key=m.requires_key,
        api_key=m.api_key,
    )


def load_config():
    """Загружает все модели из БД."""
    from backend.database import SessionLocal, Model

    db = SessionLocal()
    try:
        models = db.query(Model).order_by(Model.id).all()
        active = db.query(Model).filter(Model.is_active == True).first()
        active_id = active.model_id if active else (models[0].model_id if models else "")
        return type("AppConfig", (), {
            "models": [_db_model_to_config(m) for m in models],
            "active_model": active_id,
        })()
    finally:
        db.close()


def get_active_model() -> Optional[ModelConfig]:
    """Возвращает активную модель из БД."""
    from backend.database import SessionLocal, Model

    db = SessionLocal()
    try:
        active = db.query(Model).filter(Model.is_active == True).first()
        if active:
            return _db_model_to_config(active)
        first = db.query(Model).order_by(Model.id).first()
        return _db_model_to_config(first) if first else None
    finally:
        db.close()


def set_active_model(model_id: str) -> bool:
    """Устанавливает активную модель в БД."""
    from backend.database import SessionLocal, Model

    db = SessionLocal()
    try:
        target = db.query(Model).filter(Model.model_id == model_id).first()
        if not target:
            return False
        db.query(Model).update({Model.is_active: False})
        target.is_active = True
        db.commit()
        return True
    finally:
        db.close()

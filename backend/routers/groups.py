"""
Роутер продуктовых групп.

Продуктовая группа объединяет снимки одного продукта/документа
независимо от версии файла.

Эндпойнты:
  GET    /api/groups/              — список всех групп
  POST   /api/groups/              — создать группу
  PATCH  /api/groups/{id}          — переименовать группу
  DELETE /api/groups/{id}          — удалить группу (и все снимки в ней)
  GET    /api/groups/{id}/snapshots — снимки группы
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.database import get_db, ProductGroup, Snapshot

router = APIRouter(prefix="/api/groups", tags=["groups"])


# ── Схемы ─────────────────────────────────────────────────────────────────────

class GroupCreate(BaseModel):
    name: str

class GroupRename(BaseModel):
    name: str


# ── Сериализаторы ──────────────────────────────────────────────────────────────

def _serialize_group(g: ProductGroup) -> dict:
    return {
        "id": g.id,
        "name": g.name,
        "created_at": g.created_at.isoformat(),
        "snapshot_count": len(g.snapshots),
    }

def _serialize_snapshot(s: Snapshot) -> dict:
    return {
        "id": s.id,
        "group_id": s.group_id,
        "document_id": s.document_id,
        "document_filename": s.document_filename,
        "name": s.name,
        "role": s.role,
        "created_at": s.created_at.isoformat(),
        "data": s.data,
    }


# ── Эндпойнты ─────────────────────────────────────────────────────────────────

@router.get("/")
def list_groups(db: Session = Depends(get_db)):
    groups = db.query(ProductGroup).order_by(ProductGroup.created_at).all()
    return [_serialize_group(g) for g in groups]


@router.post("/", status_code=201)
def create_group(body: GroupCreate, db: Session = Depends(get_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Название группы не может быть пустым")
    existing = db.query(ProductGroup).filter(ProductGroup.name == name).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Группа «{name}» уже существует")
    g = ProductGroup(name=name)
    db.add(g)
    db.commit()
    db.refresh(g)
    return _serialize_group(g)


@router.patch("/{group_id}")
def rename_group(group_id: int, body: GroupRename, db: Session = Depends(get_db)):
    g = db.query(ProductGroup).filter(ProductGroup.id == group_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Группа не найдена")
    g.name = body.name.strip()
    db.commit()
    return _serialize_group(g)


@router.delete("/{group_id}", status_code=204)
def delete_group(group_id: int, db: Session = Depends(get_db)):
    g = db.query(ProductGroup).filter(ProductGroup.id == group_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Группа не найдена")
    db.delete(g)
    db.commit()


@router.get("/{group_id}/snapshots")
def list_group_snapshots(group_id: int, db: Session = Depends(get_db)):
    g = db.query(ProductGroup).filter(ProductGroup.id == group_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Группа не найдена")
    snapshots = (
        db.query(Snapshot)
        .filter(Snapshot.group_id == group_id)
        .order_by(Snapshot.created_at.desc())
        .all()
    )
    return [_serialize_snapshot(s) for s in snapshots]

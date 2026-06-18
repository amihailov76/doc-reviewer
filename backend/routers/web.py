"""
Эндпойнты для загрузки документа по URL:
- POST /api/documents/from-url        — создаёт новый документ из URL
- POST /api/documents/{id}/add-url    — добавляет страницу к существующему документу
"""

import json
import os
import sys
import subprocess
import asyncio
import traceback
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db, Document, Instruction

router = APIRouter(prefix="/api/documents", tags=["documents"])

_FETCH_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "services", "playwright_fetch.py"
)


class FromUrlRequest(BaseModel):
    url: str
    project_id: int = None


def _run_fetch(url: str) -> dict:
    """Синхронный вызов playwright_fetch.py через subprocess.run."""
    result = subprocess.run(
        [sys.executable, _FETCH_SCRIPT, url],
        capture_output=True,
        timeout=60,
    )
    stdout = result.stdout.decode("utf-8").strip()
    if not stdout:
        stderr = result.stderr.decode("utf-8").strip()
        raise RuntimeError(f"Пустой stdout. stderr: {stderr}")
    return json.loads(stdout)


def _create_instructions(db, doc_id: int, instructions: list):
    """Создаёт записи Instruction в БД из списка инструкций."""
    for item in instructions:
        instr = Instruction(
            document_id=doc_id,
            title=item["title"],
            content=item["content"],
            classification="instruction",
            page_number=None,
            section_path=item["title"][:40],
        )
        db.add(instr)


@router.post("/from-url")
async def document_from_url(body: FromUrlRequest, db: Session = Depends(get_db)):
    """Загружает страницу и создаёт новый документ."""
    url = body.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL должен начинаться с http:// или https://")

    existing = db.query(Document).filter(Document.filename == url).first()
    if existing:
        db.delete(existing)
        db.commit()

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _run_fetch, url)
    except Exception as e:
        print(f"[web.py] error: {repr(e)}\n{traceback.format_exc()}", flush=True)
        raise HTTPException(status_code=422, detail=f"Ошибка загрузки страницы: {repr(e)}")

    if not result.get("ok"):
        print(f"[web.py] fetch error: {result.get('error')}\n{result.get('tb', '')}", flush=True)
        raise HTTPException(status_code=422, detail=f"Ошибка загрузки страницы: {result.get('error')}")

    instructions = result.get("instructions", [])
    if not instructions:
        raise HTTPException(status_code=422, detail="Не удалось извлечь инструкции со страницы")

    doc = Document(
        filename=url,
        file_type="web",
        file_path="",
        project_id=body.project_id,
    )
    db.add(doc)
    db.flush()

    _create_instructions(db, doc.id, instructions)
    db.commit()
    db.refresh(doc)

    return {
        "id": doc.id,
        "filename": url,
        "file_type": "web",
        "title": result.get("title", url),
        "sections_count": len(instructions),
    }


@router.post("/{document_id}/add-url")
async def add_url_to_document(
    document_id: int,
    body: FromUrlRequest,
    db: Session = Depends(get_db),
):
    """Добавляет инструкции с новой страницы к существующему документу."""
    url = body.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL должен начинаться с http:// или https://")

    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _run_fetch, url)
    except Exception as e:
        print(f"[web.py] error: {repr(e)}\n{traceback.format_exc()}", flush=True)
        raise HTTPException(status_code=422, detail=f"Ошибка загрузки страницы: {repr(e)}")

    if not result.get("ok"):
        print(f"[web.py] fetch error: {result.get('error')}\n{result.get('tb', '')}", flush=True)
        raise HTTPException(status_code=422, detail=f"Ошибка загрузки страницы: {result.get('error')}")

    instructions = result.get("instructions", [])
    if not instructions:
        raise HTTPException(status_code=422, detail="Не удалось извлечь инструкции со страницы")

    _create_instructions(db, doc.id, instructions)
    db.commit()

    return {
        "id": doc.id,
        "added": len(instructions),
        "title": result.get("title", url),
    }

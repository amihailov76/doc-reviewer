"""
Роутер снимков оценки.

Снимки привязаны к продуктовым группам (group_id), не к документам напрямую.
document_id и document_filename хранятся как метаданные.

Эндпойнты:
  GET    /api/snapshots/document/{id}/check-evaluated  — есть ли оценки
  POST   /api/snapshots/document/{id}                  — создать снимок
  DELETE /api/snapshots/{id}                           — удалить снимок
  GET    /api/snapshots/compare                        — сравнить два снимка / снимок с текущим
  GET    /api/snapshots/document/{id}/export           — скачать XLS
"""

import io
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from backend.database import get_db, Document, Instruction, Evaluation, Snapshot, ProductGroup

router = APIRouter(prefix="/api/snapshots", tags=["snapshots"])

COLOR_RANK = {"green": 0, "yellow": 1, "orange": 2, "red": 3}
COLOR_LABEL = {"green": "Хорошо", "yellow": "Замечания", "orange": "Проблемы", "red": "Критично"}


class CreateSnapshotRequest(BaseModel):
    name: str
    role: str = "current"
    group_id: int


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


def _compute_summary(evaluated: list) -> dict:
    summary = {"green": 0, "yellow": 0, "orange": 0, "red": 0, "total": 0}
    for instr in evaluated:
        color = instr.evaluation.color
        if color in summary:
            summary[color] += 1
        summary["total"] += 1
    return summary


@router.get("/document/{document_id}/check-evaluated")
def check_evaluated(document_id: int, db: Session = Depends(get_db)):
    count = (
        db.query(Evaluation)
        .join(Instruction, Evaluation.instruction_id == Instruction.id)
        .filter(Instruction.document_id == document_id)
        .count()
    )
    return {"has_evaluations": count > 0, "count": count}


@router.get("/document/{document_id}/export")
def export_xls(document_id: int, db: Session = Depends(get_db)):
    try:
        import openpyxl
        from openpyxl.styles import PatternFill, Font, Alignment
    except ImportError:
        raise HTTPException(status_code=500, detail="openpyxl не установлен")

    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")

    instructions = (
        db.query(Instruction)
        .filter(Instruction.document_id == document_id)
        .order_by(Instruction.id)
        .all()
    )
    evaluated = [i for i in instructions if i.evaluation is not None]
    if not evaluated:
        raise HTTPException(status_code=400, detail="Нет оценённых инструкций")

    COLOR_FILLS = {
        "green":  PatternFill("solid", fgColor="C6EFCE"),
        "yellow": PatternFill("solid", fgColor="FFEB9C"),
        "orange": PatternFill("solid", fgColor="FFCC99"),
        "red":    PatternFill("solid", fgColor="FFC7CE"),
    }
    HEADER_FILL = PatternFill("solid", fgColor="2563EB")
    HEADER_FONT = Font(bold=True, color="FFFFFF")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Результаты оценки"

    headers = ["Раздел", "Стр.", "Оценка", "Рекомендации"]
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(wrap_text=True)

    for row_idx, instr in enumerate(evaluated, 2):
        ev = instr.evaluation
        recommendations = ev.recommendations or []

        rec_text = "\n".join(
            f"[{r.get('criterion', '?')}] {r.get('text', '')}"
            + (f"\nПример: {r['example']}" if r.get('example') else "")
            for r in recommendations
        )

        ws.cell(row=row_idx, column=1, value=instr.title)
        ws.cell(row=row_idx, column=2, value=instr.page_number or "")

        color_cell = ws.cell(row=row_idx, column=3, value=COLOR_LABEL.get(ev.color, ev.color or ""))
        if ev.color in COLOR_FILLS:
            color_cell.fill = COLOR_FILLS[ev.color]

        rec_cell = ws.cell(row=row_idx, column=4, value=rec_text)
        rec_cell.alignment = Alignment(wrap_text=True)

    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 6
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 80
    ws.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    safe_name = doc.filename.rsplit(".", 1)[0].replace(" ", "_")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}_review.xlsx"'},
    )


@router.post("/document/{document_id}", status_code=201)
def create_snapshot(document_id: int, body: CreateSnapshotRequest, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")

    group = db.query(ProductGroup).filter(ProductGroup.id == body.group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Продуктовая группа не найдена")

    instructions = (
        db.query(Instruction)
        .filter(Instruction.document_id == document_id)
        .order_by(Instruction.id)
        .all()
    )
    evaluated = [i for i in instructions if i.evaluation is not None]
    if not evaluated:
        raise HTTPException(status_code=400, detail="Нет оценённых инструкций. Сначала выполните оценку.")

    snapshot_data = {
        "sections": [
            {
                "title": instr.title,
                "classification": instr.classification,
                "page_number": instr.page_number,
                "color": instr.evaluation.color,
                "criteria_results": instr.evaluation.criteria_results,
                "recommendations": instr.evaluation.recommendations,
                "overrides": instr.evaluation.overrides or {},
                "model_used": instr.evaluation.model_used,
                "evaluated_at": instr.evaluation.evaluated_at.isoformat() if instr.evaluation.evaluated_at else None,
            }
            for instr in evaluated
        ],
        "summary": _compute_summary(evaluated),
    }

    if body.role == "baseline":
        db.query(Snapshot).filter(
            Snapshot.group_id == body.group_id,
            Snapshot.role == "baseline",
        ).update({"role": "current"}, synchronize_session=False)

    snapshot = Snapshot(
        group_id=body.group_id,
        document_id=document_id,
        document_filename=doc.filename,
        name=body.name or doc.filename,
        role=body.role,
        data=snapshot_data,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return _serialize_snapshot(snapshot)


@router.delete("/{snapshot_id}", status_code=204)
def delete_snapshot(snapshot_id: int, db: Session = Depends(get_db)):
    snapshot = db.query(Snapshot).filter(Snapshot.id == snapshot_id).first()
    if not snapshot:
        raise HTTPException(status_code=404, detail="Снимок не найден")
    db.delete(snapshot)
    db.commit()


@router.get("/compare")
def compare_snapshots(
    document_id: Optional[int] = Query(None),
    snapshot_a: int = Query(...),
    snapshot_b: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    snap_a = db.query(Snapshot).filter(Snapshot.id == snapshot_a).first()
    if not snap_a:
        raise HTTPException(status_code=404, detail=f"Снимок A (id={snapshot_a}) не найден")

    sections_a = snap_a.data["sections"]
    source_a = {
        "type": "snapshot", "id": snap_a.id, "name": snap_a.name,
        "role": snap_a.role, "document_filename": snap_a.document_filename,
        "created_at": snap_a.created_at.isoformat(),
    }

    if snapshot_b:
        snap_b = db.query(Snapshot).filter(Snapshot.id == snapshot_b).first()
        if not snap_b:
            raise HTTPException(status_code=404, detail=f"Снимок B (id={snapshot_b}) не найден")
        sections_b = snap_b.data["sections"]
        source_b = {
            "type": "snapshot", "id": snap_b.id, "name": snap_b.name,
            "role": snap_b.role, "document_filename": snap_b.document_filename,
            "created_at": snap_b.created_at.isoformat(),
        }
    else:
        if not document_id:
            raise HTTPException(status_code=422, detail="Укажите document_id для сравнения с текущим состоянием")
        instructions = (
            db.query(Instruction)
            .filter(Instruction.document_id == document_id)
            .order_by(Instruction.id)
            .all()
        )
        evaluated = [i for i in instructions if i.evaluation is not None]
        if not evaluated:
            raise HTTPException(status_code=400, detail="Нет оценённых инструкций для сравнения.")
        doc = db.query(Document).filter(Document.id == document_id).first()
        sections_b = [
            {"title": i.title, "classification": i.classification, "page_number": i.page_number,
             "color": i.evaluation.color, "criteria_results": i.evaluation.criteria_results,
             "overrides": i.evaluation.overrides or {}}
            for i in evaluated
        ]
        source_b = {"type": "current", "name": "Текущее состояние",
                    "document_filename": doc.filename if doc else None}

    a_by_title = {s["title"]: s for s in sections_a}
    b_by_title = {s["title"]: s for s in sections_b}
    diff = []

    for title, sec_b in b_by_title.items():
        if title not in a_by_title:
            diff.append({**sec_b, "change": "new", "color_a": None})
            continue
        sec_a = a_by_title[title]
        rank_a = COLOR_RANK.get(sec_a["color"], -1)
        rank_b = COLOR_RANK.get(sec_b["color"], -1)
        change = "improved" if rank_b < rank_a else "degraded" if rank_b > rank_a else "unchanged"
        diff.append({**sec_b, "change": change, "color_a": sec_a["color"]})

    for title, sec_a in a_by_title.items():
        if title not in b_by_title:
            diff.append({**sec_a, "change": "removed", "color_a": sec_a["color"]})

    change_order = {"degraded": 0, "new": 1, "removed": 2, "unchanged": 3, "improved": 4}
    diff.sort(key=lambda x: change_order.get(x["change"], 99))
    stats = {k: sum(1 for d in diff if d["change"] == k)
             for k in ("degraded", "improved", "unchanged", "new", "removed")}

    return {"source_a": source_a, "source_b": source_b, "diff": diff, "stats": stats}

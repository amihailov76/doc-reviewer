"""
Эндпойнты оценки инструкций:
- GET    /api/evaluation/document/{id}      — оценить весь документ (SSE-стрим прогресса)
- POST   /api/evaluation/instruction/{id}   — оценить одну инструкцию
- GET    /api/evaluation/instruction/{id}   — получить результат оценки
- DELETE /api/evaluation/document/{id}      — сбросить оценку документа
"""

import json
import queue
import threading
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.database import get_db, Document, Instruction, Evaluation, Project
from backend.services.evaluator import evaluate_instruction, EvaluationError

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])

HEARTBEAT_INTERVAL = 10    # секунд между heartbeat-пингами браузеру
INSTRUCTION_TIMEOUT = 180  # максимальное время ожидания ответа от модели (секунды)


# SSE-утилиты

def _sse_event(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

def _sse_heartbeat() -> str:
    return ": heartbeat\n\n"


# Оценка одной инструкции с heartbeat

def _call_llm_with_heartbeat(instr, q: queue.Queue,
                              product_context=None, neighbor_titles=None,
                              glossary=None):
    result_holder = [None]
    error_holder = [None]
    done_event = threading.Event()

    def worker():
        try:
            result_holder[0] = evaluate_instruction(
                title=instr.title,
                content=instr.content or "",
                product_context=product_context,
                section_path=instr.section_path,
                neighbor_titles=neighbor_titles,
                glossary=glossary,
                diff_hint=instr.diff_hint,
            )
        except EvaluationError as e:
            error_holder[0] = e
        except Exception as e:
            error_holder[0] = EvaluationError(
                message="Неожиданная ошибка при оценке",
                detail=str(e),
                advice="Попробуйте запустить оценку повторно.",
            )
        finally:
            done_event.set()

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    elapsed = 0
    while not done_event.wait(timeout=HEARTBEAT_INTERVAL):
        elapsed += HEARTBEAT_INTERVAL
        q.put(("heartbeat", None))
        if elapsed >= INSTRUCTION_TIMEOUT:
            q.put(("timeout", None))
            return

    if error_holder[0]:
        q.put(("error", error_holder[0]))
    else:
        q.put(("result", result_holder[0]))


# Оценка всего документа (SSE)

@router.get("/document/{document_id}")
def evaluate_document(document_id: int, resume: bool = False, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")

    instructions = (
        db.query(Instruction)
        .filter(
            Instruction.document_id == document_id,
            Instruction.include_in_evaluation == 1,
            Instruction.classification.in_(["instruction", "possible"]),
        )
        .order_by(Instruction.id)
        .all()
    )

    if not instructions:
        raise HTTPException(status_code=400, detail="Нет инструкций для оценки.")

    # Контекст продукта из проекта (если документ привязан к проекту)
    product_context = None
    if doc.project_id:
        project = db.query(Project).filter(Project.id == doc.project_id).first()
        if project and project.product_context:
            product_context = project.product_context

    # Карта всех разделов документа для поиска соседей
    all_doc_instrs = (
        db.query(Instruction)
        .filter(Instruction.document_id == document_id)
        .order_by(Instruction.id)
        .all()
    )
    all_ids = [i.id for i in all_doc_instrs]
    id_to_title = {i.id: i.title for i in all_doc_instrs}

    def _get_neighbor_titles(instr_id: int) -> list:
        """Возвращает заголовки 2 разделов до и 2 после текущего."""
        if instr_id not in all_ids:
            return []
        idx = all_ids.index(instr_id)
        neighbors = []
        for j in [idx - 2, idx - 1, idx + 1, idx + 2]:
            if 0 <= j < len(all_ids):
                neighbors.append(id_to_title[all_ids[j]])
        return neighbors

    def stream():
        yield _sse_event({"type": "start", "total": len(instructions)})
        summary = {"green": 0, "yellow": 0, "orange": 0, "red": 0, "errors": 0}
        done = 0

        for instr in instructions:
            done += 1

            if resume:
                existing = db.query(Evaluation).filter(
                    Evaluation.instruction_id == instr.id
                ).first()
                if existing:
                    summary[existing.color] = summary.get(existing.color, 0) + 1
                    yield _sse_event({
                        "type": "skip", "done": done, "total": len(instructions),
                        "instruction_id": instr.id, "color": existing.color, "title": instr.title,
                    })
                    continue

            neighbor_titles = _get_neighbor_titles(instr.id)
            q = queue.Queue()
            t = threading.Thread(
                target=_call_llm_with_heartbeat,
                args=(instr, q),
                kwargs={
                    "product_context": product_context,
                    "neighbor_titles": neighbor_titles,
                    "glossary": doc.glossary,
                },
                daemon=True,
            )
            t.start()

            result = None
            error = None
            aborted = False

            while True:
                msg_type, msg_val = q.get()
                if msg_type == "heartbeat":
                    yield _sse_heartbeat()
                elif msg_type == "timeout":
                    error = EvaluationError(
                        message=f"Модель не ответила за {INSTRUCTION_TIMEOUT} секунд",
                        detail=f"Таймаут: {instr.title[:60]}",
                        advice="Попробуйте переоценить раздел кнопкой ↺ или переключитесь на более быструю модель.",
                    )
                    aborted = False
                    break
                elif msg_type == "error":
                    error = msg_val
                    aborted = True
                    break
                elif msg_type == "result":
                    result = msg_val
                    break

            if aborted:
                summary["errors"] += 1
                db.rollback()
                yield _sse_event({
                    "type": "error", "instruction_id": instr.id, "title": instr.title,
                    "message": error.message, "advice": error.advice,
                })
                yield _sse_event({"type": "done", "summary": summary, "aborted": True})
                return

            if error:
                summary["errors"] += 1
                yield _sse_event({
                    "type": "error", "instruction_id": instr.id, "title": instr.title,
                    "message": error.message, "advice": error.advice,
                })
                continue

            try:
                evaluation = db.query(Evaluation).filter(Evaluation.instruction_id == instr.id).first()
                if evaluation:
                    evaluation.color = result.color
                    evaluation.criteria_results = result.criteria_results
                    evaluation.recommendations = result.recommendations
                    evaluation.model_used = result.model_used
                    evaluation.evaluated_at = datetime.utcnow()
                    # overrides не трогаем — пользователь ставил их осознанно
                else:
                    evaluation = Evaluation(
                        instruction_id=instr.id, color=result.color,
                        criteria_results=result.criteria_results,
                        recommendations=result.recommendations,
                        model_used=result.model_used,
                        overrides={},
                    )
                    db.add(evaluation)
                db.commit()
            except Exception:
                db.rollback()

            summary[result.color] = summary.get(result.color, 0) + 1
            yield _sse_event({
                "type": "progress", "done": done, "total": len(instructions),
                "instruction_id": instr.id, "color": result.color, "title": instr.title,
            })

        doc.last_evaluated_at = datetime.utcnow()
        db.commit()
        yield _sse_event({"type": "done", "summary": summary, "aborted": False})

    return StreamingResponse(stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# Оценка одной инструкции

@router.post("/instruction/{instruction_id}")
def evaluate_single(instruction_id: int, db: Session = Depends(get_db)):
    instr = db.query(Instruction).filter(Instruction.id == instruction_id).first()
    if not instr:
        raise HTTPException(status_code=404, detail="Инструкция не найдена")

    doc = db.query(Document).filter(Document.id == instr.document_id).first()

    # Контекст продукта из проекта
    product_context = None
    if doc and doc.project_id:
        project = db.query(Project).filter(Project.id == doc.project_id).first()
        if project and project.product_context:
            product_context = project.product_context

    # Соседние разделы
    all_doc_instrs = (
        db.query(Instruction)
        .filter(Instruction.document_id == instr.document_id)
        .order_by(Instruction.id)
        .all()
    )
    all_ids = [i.id for i in all_doc_instrs]
    id_to_title = {i.id: i.title for i in all_doc_instrs}
    neighbor_titles = []
    if instr.id in all_ids:
        idx = all_ids.index(instr.id)
        for j in [idx - 2, idx - 1, idx + 1, idx + 2]:
            if 0 <= j < len(all_ids):
                neighbor_titles.append(id_to_title[all_ids[j]])

    try:
        result = evaluate_instruction(
            title=instr.title, content=instr.content or "",
            product_context=product_context,
            section_path=instr.section_path,
            neighbor_titles=neighbor_titles,
            glossary=doc.glossary if doc else None,
            diff_hint=instr.diff_hint,
        )
    except EvaluationError as e:
        raise HTTPException(status_code=502, detail={"message": e.message, "advice": e.advice})

    evaluation = db.query(Evaluation).filter(Evaluation.instruction_id == instruction_id).first()
    if evaluation:
        evaluation.color = result.color
        evaluation.criteria_results = result.criteria_results
        evaluation.recommendations = result.recommendations
        evaluation.model_used = result.model_used
        evaluation.evaluated_at = datetime.utcnow()
        # overrides не трогаем — пользователь ставил их осознанно
    else:
        evaluation = Evaluation(
            instruction_id=instruction_id, color=result.color,
            criteria_results=result.criteria_results,
            recommendations=result.recommendations,
            model_used=result.model_used,
            overrides={},
        )
        db.add(evaluation)

    db.commit()
    db.refresh(evaluation)
    return _serialize_evaluation(evaluation)


@router.get("/instruction/{instruction_id}")
def get_evaluation(instruction_id: int, db: Session = Depends(get_db)):
    evaluation = db.query(Evaluation).filter(Evaluation.instruction_id == instruction_id).first()
    if not evaluation:
        raise HTTPException(status_code=404, detail="Оценка не найдена")
    return _serialize_evaluation(evaluation)


@router.delete("/document/{document_id}")
def reset_evaluation(document_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")

    instruction_ids = [i.id for i in db.query(Instruction.id).filter(Instruction.document_id == document_id).all()]
    deleted = db.query(Evaluation).filter(Evaluation.instruction_id.in_(instruction_ids)).delete(synchronize_session=False)
    doc.last_evaluated_at = None
    db.commit()
    return {"ok": True, "deleted": deleted}


def _serialize_evaluation(evaluation: Evaluation) -> dict:
    return {
        "id": evaluation.id,
        "instruction_id": evaluation.instruction_id,
        "color": evaluation.color,
        "criteria_results": evaluation.criteria_results,
        "recommendations": evaluation.recommendations,
        "overrides": evaluation.overrides or {},
        "model_used": evaluation.model_used,
        "evaluated_at": evaluation.evaluated_at.isoformat() if evaluation.evaluated_at else None,
    }

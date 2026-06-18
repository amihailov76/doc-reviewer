"""
Сервис сравнения версий документа при замене файла.

Логика:
- Сопоставляет разделы старой и новой версии документа по заголовкам
- Вычисляет степень схожести содержимого через SequenceMatcher
- Для почти неизменившихся разделов (ratio > 0.95) — переносит старую оценку
- Для частично изменившихся (0.6 ≤ ratio ≤ 0.95) — сохраняет краткое описание изменений
- Кардинально изменившиеся и новые разделы оцениваются с нуля
"""

import difflib
import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

# Пороги схожести содержимого
RATIO_COPY   = 0.95   # выше — раздел не изменился, копируем оценку
RATIO_HINT   = 0.60   # выше — раздел изменился частично, добавляем diff_hint
# Ниже RATIO_HINT — раздел кардинально изменился или новый, оцениваем с нуля

# Порог схожести заголовков для сопоставления разделов
TITLE_MATCH_RATIO = 0.70


@dataclass
class SectionMatch:
    """Результат сопоставления одного раздела новой версии со старой."""
    new_title: str
    old_title: Optional[str]        # None — раздел новый, пары не найдено
    ratio: float                    # схожесть содержимого (0.0–1.0)
    action: str                     # "copy" | "hint" | "fresh"
    diff_hint: Optional[str]        # краткое описание изменений (только для "hint")
    old_evaluation: Optional[dict]  # оценка из старой версии (только для "copy")


def _title_similarity(a: str, b: str) -> float:
    """Степень схожести двух заголовков (без учёта регистра)."""
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _content_similarity(old: str, new: str) -> float:
    """Степень схожести содержимого двух разделов."""
    old = old or ""
    new = new or ""
    if not old and not new:
        return 1.0
    if not old or not new:
        return 0.0
    return difflib.SequenceMatcher(None, old, new).ratio()


def _make_diff_hint(old_content: str, new_content: str) -> str:
    """
    Формирует краткое текстовое описание изменений между двумя версиями раздела.
    Используется для подсказки LLM при переоценке.
    """
    old_lines = (old_content or "").splitlines(keepends=True)
    new_lines = (new_content or "").splitlines(keepends=True)

    added   = sum(1 for line in new_lines if line not in old_lines)
    removed = sum(1 for line in old_lines if line not in new_lines)

    parts = []
    if removed:
        parts.append(f"удалено строк: {removed}")
    if added:
        parts.append(f"добавлено строк: {added}")

    if not parts:
        return "незначительные изменения форматирования"

    # Добавляем примеры изменённых строк (до 2 штук) для контекста
    diff = list(difflib.unified_diff(
        old_lines, new_lines, lineterm="", n=0
    ))
    examples = []
    for line in diff:
        if line.startswith(("---", "+++", "@@")):
            continue
        stripped = line[1:].strip()
        if stripped and len(stripped) > 10:
            prefix = "добавлено" if line.startswith("+") else "удалено"
            examples.append(f"{prefix}: «{stripped[:80]}»")
        if len(examples) >= 2:
            break

    hint = ", ".join(parts)
    if examples:
        hint += ". " + "; ".join(examples)
    return hint


def match_sections(
    old_instructions: list,
    new_instructions: list,
) -> list[SectionMatch]:
    """
    Сопоставляет разделы новой версии документа с разделами старой.

    Параметры:
        old_instructions — список Instruction из БД (старая версия)
        new_instructions — список Instruction из БД (новая версия)

    Возвращает:
        Список SectionMatch — по одному элементу для каждого раздела новой версии.
    """
    # Строим индекс старых разделов по заголовку для быстрого поиска
    old_by_title = {instr.title: instr for instr in old_instructions}

    results = []

    for new_instr in new_instructions:
        # 1. Пробуем точное совпадение заголовка
        old_instr = old_by_title.get(new_instr.title)

        # 2. Если точного нет — ищем ближайший по схожести заголовка
        if old_instr is None:
            best_ratio = 0.0
            for candidate in old_instructions:
                r = _title_similarity(new_instr.title, candidate.title)
                if r > best_ratio:
                    best_ratio = r
                    if r >= TITLE_MATCH_RATIO:
                        old_instr = candidate

        # 3. Нет пары — новый раздел
        if old_instr is None:
            results.append(SectionMatch(
                new_title=new_instr.title,
                old_title=None,
                ratio=0.0,
                action="fresh",
                diff_hint=None,
                old_evaluation=None,
            ))
            continue

        # 4. Пара найдена — считаем схожесть содержимого
        ratio = _content_similarity(old_instr.content, new_instr.content)

        if ratio >= RATIO_COPY:
            # Раздел не изменился — переносим оценку
            old_eval = None
            if old_instr.evaluation:
                old_eval = {
                    "color":            old_instr.evaluation.color,
                    "criteria_results": old_instr.evaluation.criteria_results,
                    "recommendations":  old_instr.evaluation.recommendations,
                    "model_used":       old_instr.evaluation.model_used,
                    "overrides":        old_instr.evaluation.overrides or {},
                }
            results.append(SectionMatch(
                new_title=new_instr.title,
                old_title=old_instr.title,
                ratio=ratio,
                action="copy" if old_eval else "fresh",
                diff_hint=None,
                old_evaluation=old_eval,
            ))

        elif ratio >= RATIO_HINT:
            # Раздел изменился частично — сохраняем подсказку
            hint = _make_diff_hint(old_instr.content, new_instr.content)
            results.append(SectionMatch(
                new_title=new_instr.title,
                old_title=old_instr.title,
                ratio=ratio,
                action="hint",
                diff_hint=hint,
                old_evaluation=None,
            ))

        else:
            # Кардинально изменился — оцениваем с нуля
            results.append(SectionMatch(
                new_title=new_instr.title,
                old_title=old_instr.title,
                ratio=ratio,
                action="fresh",
                diff_hint=None,
                old_evaluation=None,
            ))

    return results

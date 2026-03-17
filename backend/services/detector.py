"""
Детектор инструкций — классифицирует разделы документа по трём признакам.

Признак 1: заголовок содержит отглагольное существительное (девербатив).
    Определяется через pymorphy2: ищем слово с тегом NOUN, производное от глагола.
    Надёжные суффиксы девербативов: -ание/-яние, -ение/-яение, -ировка, -овка,
    -ация/-яция, -тие, -ство (в контексте процесса), -ка (в контексте действия).
    pymorphy2 даёт граммему, но не всегда прямо указывает «девербатив», поэтому
    используем комбинацию: морфологический тег NOUN + список продуктивных суффиксов.

Признак 2: тело раздела содержит титульную фразу со словом «чтобы».
    Ищем строки вида «Чтобы <глагол>...» или «чтобы <глагол>...» с двоеточием
    в конце строки или в конце предложения.

Признак 3: тело раздела содержит нумерованный список.
    Ищем строки, начинающиеся с «1.», «1)», «1 .» и т.п.

Итоговая классификация:
    - все три признака → "instruction"
    - один или два признака → "possible"
    - ноль признаков → "non-instruction"
"""

import re
import pymorphy3 as pymorphy2  # pymorphy3 — совместимый форк для Python 3.11+
from functools import lru_cache
from typing import NamedTuple

# ── Инициализация анализатора ─────────────────────────────────────────────────
# MorphAnalyzer создаётся один раз и переиспользуется — загрузка словарей занимает
# ~0.5 сек, создавать при каждом вызове нельзя.
_morph = pymorphy2.MorphAnalyzer()


# ── Суффиксы отглагольных существительных (девербативов) ─────────────────────
# Список составлен на основе продуктивных словообразовательных моделей русского языка.
# Суффиксы упорядочены от длинных к коротким, чтобы более специфичные проверялись первыми.
DEVERBAL_SUFFIXES = (
    "ирование", "ирования", "ированию", "ированием",  # конфигурирование
    "изирование", "изации",                            # авторизация, оптимизация
    "ирование", "ировка", "ировки", "ировке",          # настройка → настраивание
    "ование", "овании", "ованию", "ованием",           # сохранение (сохранование)
    "ация", "ации", "ацию", "ацией",                   # авторизация, настройка
    "яция", "яции",                                    # вариация
    "ение", "ения", "ению", "енией", "ением",          # добавление, создание
    "ание", "ания", "анию", "анием",                   # сохранение, назначание
    "яние", "яния", "янию", "янием",                   # управление
    "тие", "тия", "тию", "тием",                       # открытие, закрытие
    "овка", "овки", "овке", "овкой",                   # настройка, блокировка
    "евка", "евки",                                    # шифровка
    "ёвка", "ёвки",
)


@lru_cache(maxsize=4096)
def _is_deverbal_noun(word: str) -> bool:
    """
    Проверяет, является ли слово отглагольным существительным.

    Стратегия:
    1. pymorphy2 должен распознать слово как существительное (NOUN).
    2. Слово должно оканчиваться на один из продуктивных суффиксов девербативов.

    Кеш lru_cache(4096) позволяет не анализировать одно слово дважды.
    """
    word_lower = word.lower()

    # Быстрая проверка суффикса до морфологического анализа
    has_suffix = any(word_lower.endswith(s) for s in DEVERBAL_SUFFIXES)
    if not has_suffix:
        return False

    # Морфологический анализ: ищем разбор с тегом NOUN
    parses = _morph.parse(word_lower)
    for p in parses:
        if "NOUN" in p.tag and p.score > 0.1:  # score — уверенность анализатора
            return True

    return False


def has_deverbal_noun_in_title(title: str) -> bool:
    """
    Признак 1: заголовок содержит отглагольное существительное.
    Проверяем каждое слово заголовка длиннее 4 символов.
    """
    words = re.findall(r"[а-яёА-ЯЁ]{5,}", title)
    return any(_is_deverbal_noun(w) for w in words)


def has_purpose_phrase(content: str) -> bool:
    """
    Признак 2: тело раздела содержит титульную фразу со словом «чтобы».

    Ищем паттерны:
    - «Чтобы <что-то сделать>:»  — строка заканчивается двоеточием
    - «► Чтобы ...»               — со спецсимволом-маркером перед фразой
    - «чтобы <что-то сделать>»   — в любом месте строки

    Достаточно одного вхождения в любом месте тела раздела.
    """
    # Паттерн 1: «чтобы» после любых символов (включая ►, пробелы) + двоеточие в конце
    pattern_colon = re.compile(
        r"[Чч]тобы\s+\w.{3,120}:",
        re.MULTILINE,
    )
    if pattern_colon.search(content):
        return True

    # Паттерн 2: «чтобы» в начале строки или после пробельных/спецсимволов
    pattern_start = re.compile(
        r"(?:^|[\s\W])[Чч]тобы\s+[а-яёА-ЯЁ]",
        re.MULTILINE,
    )
    if pattern_start.search(content):
        return True

    return False


def has_numbered_steps(content: str) -> bool:
    """
    Признак 3: тело раздела содержит нумерованный список шагов.

    Требования:
    - Хотя бы два пункта с цифрами и разделителем (точка или скобка).
    - Список начинается с «1.» или «1)» — это отсекает оглавления вида
      «4.1 Раздел», «4.2 Раздел», которые не являются пошаговыми инструкциями.

    Примеры распознаваемых форматов:
        1. Откройте меню.
        1) Нажмите кнопку.
    """
    # Ищем строки вида «N. текст» или «N) текст»
    pattern = re.compile(
        r"^\s*(\d+)\s*[.)]\s+\S",
        re.MULTILINE,
    )
    matches = pattern.findall(content)

    if len(matches) < 2:
        return False

    # Список должен начинаться с 1 — признак пошаговой инструкции,
    # а не оглавления или перечня ссылок
    return "1" in matches


# ── Исключения — заголовки, которые никогда не являются инструкциями ──────────
# Разделы с этими подстроками в заголовке получают классификацию "non-instruction"
# независимо от наличия признаков 1–3.
EXCLUDED_TITLE_FRAGMENTS = (
    "условные обозначения",
    "другие источники информации",
)

EXCLUDED_TITLE_PREFIXES = (
    "содержание",
)


def _is_excluded_title(title: str) -> bool:
    """Возвращает True если заголовок соответствует одному из исключений."""
    title_lower = title.strip().lower()
    if any(fragment in title_lower for fragment in EXCLUDED_TITLE_FRAGMENTS):
        return True
    if any(title_lower.startswith(prefix) for prefix in EXCLUDED_TITLE_PREFIXES):
        return True
    return False

class DetectionResult(NamedTuple):
    classification: str   # "instruction" / "possible" / "non-instruction"
    sign1_deverbal: bool  # признак 1: отглагольное существительное в заголовке
    sign2_purpose: bool   # признак 2: фраза с «чтобы»
    sign3_numbered: bool  # признак 3: нумерованные шаги


def classify_section(title: str, content: str) -> DetectionResult:
    """
    Классифицирует раздел документа по трём признакам.

    Возвращает DetectionResult с итоговой классификацией и значениями каждого признака.
    """
    # Исключения: заголовки, которые заведомо не являются инструкциями
    if _is_excluded_title(title):
        return DetectionResult(
            classification="non-instruction",
            sign1_deverbal=False,
            sign2_purpose=False,
            sign3_numbered=False,
        )

    s1 = has_deverbal_noun_in_title(title)
    s2 = has_purpose_phrase(content)
    s3 = has_numbered_steps(content)

    score = sum([s1, s2, s3])

    if score == 3:
        classification = "instruction"
    elif score >= 1:
        classification = "possible"
    else:
        classification = "non-instruction"

    return DetectionResult(
        classification=classification,
        sign1_deverbal=s1,
        sign2_purpose=s2,
        sign3_numbered=s3,
    )

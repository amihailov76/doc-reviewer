"""
Парсер PDF-документов через PyMuPDF.

Стратегия определения заголовков:
- Собираем статистику размеров шрифтов по всему документу.
- Медианный размер — это «основной текст».
- Блоки, которые крупнее медианы на заданный порог, считаем заголовками.
- Уровень заголовка определяется по относительному размеру шрифта.

Ограничение: работает надёжно для PDF с настоящим текстом (не сканов).
"""

import fitz  # PyMuPDF
from statistics import median
from .base import Section, ParseResult, make_untitled_title


import re

# Насколько шрифт должен быть крупнее медианы, чтобы считаться заголовком
HEADING_SIZE_THRESHOLD = 1.15   # +15% от медианного размера

# Минимальный размер шрифта для заголовка (отсекает сноски и подписи)
MIN_HEADING_SIZE = 10.0

# Минимальная длина текста блока, чтобы считать его заголовком
MIN_HEADING_TEXT_LEN = 4

# Паттерны, по которым блок считается телом текста, даже если шрифт крупный.
# Типичные случаи в технической документации:
# - «► Чтобы сделать что-то:» — титульная фраза инструкции
# - «Чтобы ...» — то же без маркера
# - «В этом разделе:» — навигационный блок оглавления внутри раздела
# - «См. также» — навигационный блок ссылок в конце раздела
# - строки с тире/дефисом в начале — пункты маркированного списка
# - строки, начинающиеся с символа-заменителя □ (U+25A1) — артефакты символьных шрифтов
#
# ВАЖНО: паттерн нумерации «^\d+\.\s» намеренно убран из этого списка.
# Он ошибочно матчил заголовки разделов вида «2. О продукте», «10. Решение проблем».
# Нумерованные шаги инструкций имеют обычный размер шрифта и не попадают
# в эту проверку (она применяется только к блокам с крупным шрифтом, level > 0).
_BODY_TEXT_PATTERNS = re.compile(
    r"^(?:[►▶•]\s*)?[Чч]тобы\s"
    r"|^[Вв]\s+этом\s+разделе"
    r"|^[Сс]м\.?\s+также"
    r"|^[\-\—\–]\s+\S"
    r"|^[\u25A1\u25AA\u25CF\u2022\u25B6]\s*"
    r"|^[\uE000-\uF8FF]",
    re.MULTILINE,
)

# Паттерн для определения «мусорных» блоков из символьных шрифтов:
# блок состоит преимущественно из непечатаемых или спецсимволов,
# включая Private Use Area (PUA) — диапазон \uE000–\uF8FF,
# который используется шрифтами-иконками (✓, ⚠ и аналогичные в PDF)
_SYMBOL_FONT_RE = re.compile(r"^[\u0080-\u00FF\u25A0-\u25FF\uE000-\uF8FF\uF000-\uFFFF\s]+$")


def _is_garbage_block(text: str) -> bool:
    """
    Проверяет, является ли блок артефактом символьного шрифта или мусорным блоком.
    Такие блоки не несут текстового смысла и не должны становиться разделами.
    """
    stripped = text.strip()
    if not stripped:
        return True
    # Блок из одного-двух символов — иконка или разделитель
    if len(stripped) <= 2:
        return True
    # Блок состоит только из спецсимволов/непечатаемых/PUA-символов
    if _SYMBOL_FONT_RE.match(stripped):
        return True
    # Блок состоит только из тире/дефисов и пробелов — артефакт переноса строки
    if re.match(r"^[\-\—\–\s]+$", stripped):
        return True
    return False


def _clean_pua(text: str) -> str:
    """
    Заменяет символы из Private Use Area на текстовую метку [иконка].
    PUA-диапазон (U+E000–U+F8FF) используется шрифтами-иконками в PDF.
    Замена вместо удаления позволяет LLM понять, что здесь был визуальный
    элемент (кнопка, маркер, значок), а не пропуск в тексте.
    Несколько подряд идущих PUA-символов схлопываются в одну метку.
    """
    return re.sub(r"[\uE000-\uF8FF]+", "[иконка]", text).strip()


def _collect_font_sizes(doc: fitz.Document) -> list[float]:
    """Собирает все размеры шрифтов из документа для статистики."""
    sizes = []
    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if block["type"] != 0:  # только текстовые блоки
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    if span["text"].strip():
                        sizes.append(span["size"])
    return sizes


def _classify_size(size: float, median_size: float) -> int:
    """Возвращает уровень заголовка (1–4) или 0 для обычного текста."""
    if size < MIN_HEADING_SIZE:
        return 0
    ratio = size / median_size
    if ratio >= 1.6:
        return 1
    if ratio >= 1.4:
        return 2
    if ratio >= HEADING_SIZE_THRESHOLD + 0.1:
        return 3
    if ratio >= HEADING_SIZE_THRESHOLD:
        return 4
    return 0


def _is_bold(span: dict) -> bool:
    return bool(span.get("flags", 0) & 16)  # бит 4 = bold


def parse_pdf(file_path: str) -> ParseResult:
    doc = fitz.open(file_path)
    sections: list[Section] = []
    raw_lines: list[str] = []

    # Шаг 1: статистика размеров шрифтов
    all_sizes = _collect_font_sizes(doc)
    if not all_sizes:
        return ParseResult(sections=[], raw_text="")
    median_size = median(all_sizes)

    # Шаг 2: проход по страницам
    current_title = "(введение)"
    current_level = 0
    current_lines: list[str] = []
    current_page = 1

    def flush(title: str, level: int, lines: list[str], page: int):
        content = "\n".join(lines).strip()
        if not content and level == 0:
            return
        if not title and content:
            title = make_untitled_title(content)
        sections.append(Section(
            title=title,
            level=level,
            content=content,
            page_number=page,
        ))

    for page_num, page in enumerate(doc, start=1):
        blocks = page.get_text("dict")["blocks"]

        for block in blocks:
            if block["type"] != 0:
                continue

            # Собираем текст блока и определяем его «уровень»
            block_text_parts = []
            block_max_size = 0.0
            block_is_bold = False

            for line in block["lines"]:
                line_text = ""
                for span in line["spans"]:
                    line_text += span["text"]
                    # Учитываем размер спана только если он содержит реальный текст,
                    # а не только PUA-символы (иконки из символьных шрифтов)
                    span_clean = _clean_pua(span["text"]).strip()
                    if span_clean and span["size"] > block_max_size:
                        block_max_size = span["size"]
                    if _is_bold(span):
                        block_is_bold = True
                block_text_parts.append(line_text)

            block_text = " ".join(block_text_parts).strip()
            if not block_text:
                continue

            # Заменяем PUA-символы на [иконка] ДО проверки на мусор —
            # иначе одиночные иконки (например маркеры списков) отбрасываются
            # и LLM видит пропуск в тексте вместо визуального элемента.
            block_text = _clean_pua(block_text)
            if not block_text:
                continue

            # Пропускаем блоки из символьных шрифтов — они не несут текстового смысла.
            # Блоки с [иконка] сюда не попадают — они уже содержат читаемый текст.
            if _is_garbage_block(block_text):
                continue

            raw_lines.append(block_text)

            level = _classify_size(block_max_size, median_size)

            # Даже если шрифт крупный — не считаем заголовком:
            # 1. строки с титульными фразами («Чтобы...», тире-списки и т.п.)
            # 2. слишком короткие блоки (артефакты символьных шрифтов)
            if level > 0 and (
                _BODY_TEXT_PATTERNS.match(block_text)
                or len(block_text.strip()) < MIN_HEADING_TEXT_LEN
            ):
                level = 0

            if level > 0:
                flush(current_title, current_level, current_lines, current_page)
                current_title = block_text
                current_level = level
                current_lines = []
                current_page = page_num
            else:
                current_lines.append(block_text)

    flush(current_title, current_level, current_lines, current_page)
    doc.close()

    return ParseResult(
        sections=sections,
        raw_text="\n".join(raw_lines),
    )

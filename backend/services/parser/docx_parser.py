"""
Парсер DOCX-документов.

Стратегия:
- Проходим по параграфам документа в порядке следования.
- Параграфы со стилями Heading 1–4 становятся разделами дерева.
- Текст между заголовками накапливается как content текущего раздела.
- Параграфы до первого заголовка объединяются в корневой раздел «(введение)».
"""

from docx import Document
from docx.oxml.ns import qn
from .base import Section, ParseResult, make_untitled_title


# Стили Word, которые считаем заголовками (русские и английские варианты)
HEADING_STYLES = {
    "heading 1": 1, "heading 2": 2, "heading 3": 3, "heading 4": 4,
    "заголовок 1": 1, "заголовок 2": 2, "заголовок 3": 3, "заголовок 4": 4,
}


def _get_heading_level(paragraph) -> int:
    """Возвращает уровень заголовка (1–4) или 0, если параграф — не заголовок."""
    style_name = paragraph.style.name.lower() if paragraph.style else ""

    # Проверяем стиль по имени
    for key, level in HEADING_STYLES.items():
        if style_name.startswith(key):
            return level

    # Проверяем outline level в XML (некоторые шаблоны используют его вместо стиля)
    pPr = paragraph._p.find(qn("w:pPr"))
    if pPr is not None:
        outlineLvl = pPr.find(qn("w:outlineLvl"))
        if outlineLvl is not None:
            val = int(outlineLvl.get(qn("w:val"), 9))
            if val < 4:
                return val + 1

    return 0


def parse_docx(file_path: str) -> ParseResult:
    doc = Document(file_path)
    sections: list[Section] = []
    raw_lines: list[str] = []

    current_title = "(введение)"
    current_level = 0
    current_lines: list[str] = []

    def flush(title: str, level: int, lines: list[str]):
        """Сохраняет накопленный текст как раздел."""
        content = "\n".join(lines).strip()
        if not content and level == 0:
            return  # пропускаем пустое введение
        if not title and content:
            title = make_untitled_title(content)
        sections.append(Section(
            title=title,
            level=level,
            content=content,
        ))

    for para in doc.paragraphs:
        text = para.text.strip()
        raw_lines.append(text)

        level = _get_heading_level(para)
        if level > 0:
            flush(current_title, current_level, current_lines)
            current_title = text or make_untitled_title("")
            current_level = level
            current_lines = []
        else:
            if text:
                current_lines.append(text)

    # Сохраняем последний раздел
    flush(current_title, current_level, current_lines)

    return ParseResult(
        sections=sections,
        raw_text="\n".join(raw_lines),
    )

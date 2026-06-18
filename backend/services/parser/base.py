from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Section:
    """Один раздел документа — заголовок + текст тела."""
    title: str                        # текст заголовка (или первые N символов тела)
    level: int                        # уровень вложенности: 1..4
    content: str                      # полный текст тела раздела
    page_number: Optional[int] = None # номер страницы (для PDF/DOCX)
    section_path: str = ""            # путь в дереве: "1 > 1.2 > 1.2.3"
    children: list = field(default_factory=list)  # вложенные Section


@dataclass
class ParseResult:
    """Результат парсинга документа."""
    sections: list[Section]           # плоский список всех разделов в порядке документа
    raw_text: str = ""                # полный текст документа (для отладки)


# Количество символов для заголовка раздела без явного заголовка
UNTITLED_PREVIEW_LEN = 60


def make_untitled_title(text: str) -> str:
    """Формирует заголовок из первых N символов текста."""
    preview = text.strip()[:UNTITLED_PREVIEW_LEN].replace("\n", " ")
    if len(text.strip()) > UNTITLED_PREVIEW_LEN:
        preview += "…"
    return preview or "(пустой раздел)"

"""
Парсер MD и TXT файлов.

Для Markdown:
- Строки, начинающиеся с #, ## и т.д. — заголовки уровней 1–4.
- Остальное — тело текущего раздела.

Для TXT:
- Коротких строк в верхнем регистре или заканчивающихся на ':' — эвристика заголовка.
- Всё остальное — тело.
"""

import re
from .base import Section, ParseResult, make_untitled_title


def parse_md(file_path: str) -> ParseResult:
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    sections: list[Section] = []
    current_title = "(введение)"
    current_level = 0
    current_lines: list[str] = []

    def flush(title, level, lines):
        content = "\n".join(lines).strip()
        if not content and level == 0:
            return
        if not title and content:
            title = make_untitled_title(content)
        sections.append(Section(title=title, level=level, content=content))

    for line in text.splitlines():
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            flush(current_title, current_level, current_lines)
            current_level = len(m.group(1))
            current_title = m.group(2).strip()
            current_lines = []
        else:
            stripped = line.strip()
            if stripped:
                current_lines.append(stripped)

    flush(current_title, current_level, current_lines)

    return ParseResult(sections=sections, raw_text=text)


def parse_txt(file_path: str) -> ParseResult:
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    sections: list[Section] = []
    current_title = "(введение)"
    current_level = 0
    current_lines: list[str] = []

    def flush(title, level, lines):
        content = "\n".join(lines).strip()
        if not content and level == 0:
            return
        if not title and content:
            title = make_untitled_title(content)
        sections.append(Section(title=title, level=level, content=content))

    def _looks_like_heading(line: str) -> bool:
        """Эвристика для TXT: короткая строка, целиком в верхнем регистре или
        заканчивается двоеточием и не является предложением."""
        stripped = line.strip()
        if not stripped or len(stripped) > 120:
            return False
        if stripped == stripped.upper() and len(stripped) > 3 and stripped.isalpha() is False:
            # Верхний регистр с цифрами/пробелами — вероятно заголовок раздела
            return True
        if stripped.endswith(":") and len(stripped.split()) <= 8:
            return True
        return False

    for line in text.splitlines():
        if _looks_like_heading(line):
            flush(current_title, current_level, current_lines)
            current_title = line.strip().rstrip(":")
            current_level = 2  # все эвристические заголовки TXT — уровень 2
            current_lines = []
        else:
            stripped = line.strip()
            if stripped:
                current_lines.append(stripped)

    flush(current_title, current_level, current_lines)

    return ParseResult(sections=sections, raw_text=text)

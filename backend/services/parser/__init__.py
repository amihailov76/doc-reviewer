"""
Единая точка входа для парсинга документов.
Выбирает нужный парсер по расширению файла.
"""

import os
from .base import ParseResult
from .pdf_parser import parse_pdf
from .docx_parser import parse_docx
from .text_parser import parse_md, parse_txt


def parse_document(file_path: str) -> ParseResult:
    """Парсит документ и возвращает список разделов."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return parse_pdf(file_path)
    elif ext == ".docx":
        return parse_docx(file_path)
    elif ext == ".md":
        return parse_md(file_path)
    elif ext == ".txt":
        return parse_txt(file_path)
    else:
        raise ValueError(f"Неподдерживаемый формат файла: {ext}")

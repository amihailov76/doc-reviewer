# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec для doc-reviewer.

Запуск сборки:
    pyinstaller doc_reviewer.spec

Результат: dist/doc-reviewer.exe
"""

import os
from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None

# ── Собираем все данные и бинарники зависимостей ────────────────────────────

datas = []
binaries = []
hiddenimports = []

# PyMuPDF (fitz) — нужны нативные библиотеки
fitz_datas, fitz_binaries, fitz_hidden = collect_all("fitz")
datas += fitz_datas
binaries += fitz_binaries
hiddenimports += fitz_hidden

# python-docx — шаблоны и данные
datas += collect_data_files("docx")

# pymorphy3 — словари для морфологического анализа
pymorphy3_datas, _, pymorphy3_hidden = collect_all("pymorphy3")
datas += pymorphy3_datas
hiddenimports += pymorphy3_hidden

datas += collect_data_files("pymorphy3_dicts_ru")

# uvicorn — стандартные компоненты
hiddenimports += [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
]

# SQLAlchemy диалекты
hiddenimports += [
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.pool",
]

# Прочие зависимости
hiddenimports += [
    "aiofiles",
    "multipart",
    "python_multipart",
    "httpx",
    "openpyxl",
    "yaml",
    "playwright",
    "playwright.sync_api",
]

# Все модули бэкенда — явно перечисляем чтобы PyInstaller не пропустил
hiddenimports += [
    "backend",
    "backend.main",
    "backend.database",
    "backend.config",
    "backend.routers",
    "backend.routers.config_router",
    "backend.routers.documents",
    "backend.routers.instructions",
    "backend.routers.evaluation",
    "backend.routers.snapshots",
    "backend.routers.groups",
    "backend.routers.web",
    "backend.services",
    "backend.services.evaluator",
    "backend.services.detector",
    "backend.services.parser",
    "backend.services.parser.pdf_parser",
    "backend.services.parser.docx_parser",
    "backend.services.parser.base",
]

# ── Фронтенд (собранный Vite) ────────────────────────────────────────────────
datas += [
    ("frontend/dist", "frontend/dist"),
]

# ── Файлы конфигурации ───────────────────────────────────────────────────────
datas += [
    ("models.yml",   "."),
    ("criteria.md",  "."),
]

# ── Сборка ───────────────────────────────────────────────────────────────────

a = Analysis(
    ["run_prod.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "PIL"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
    module_collection_mode={"backend": "py"},
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="doc-reviewer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # без консольного окна
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

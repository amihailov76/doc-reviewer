import sys
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import os
import sys
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

from backend.database import init_db
from backend.routers.config_router import router as config_router

from backend.routers.documents import router as documents_router
from backend.routers.instructions import router as instructions_router
from backend.routers.evaluation import router as evaluation_router
from backend.routers.snapshots import router as snapshots_router
from backend.routers.groups import router as groups_router
from backend.routers.web import router as web_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Инициализация при старте приложения."""
    init_db()
    yield


app = FastAPI(
    title="doc-reviewer",
    description="Инструмент для оценки полноты инструкций в технической документации",
    version="0.1.0",
    lifespan=lifespan,
)

# Подключаем роутеры
app.include_router(config_router)
app.include_router(documents_router)
app.include_router(instructions_router)
app.include_router(evaluation_router)
app.include_router(snapshots_router)
app.include_router(groups_router)
app.include_router(web_router)


@app.get("/api/ping")
def ping():
    """Тестовый эндпойнт для проверки работы бэкенда."""
    return {"status": "ok", "message": "doc-reviewer работает"}


# Раздача фронтенда как статики
# Путь к dist/ — рядом с main.py при сборке, или в frontend/dist/ при разработке
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIST = os.path.join(BASE_DIR, "frontend", "dist")

if os.path.exists(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        """Возвращает index.html для всех маршрутов (SPA-режим)."""
        index = os.path.join(FRONTEND_DIST, "index.html")
        return FileResponse(index)

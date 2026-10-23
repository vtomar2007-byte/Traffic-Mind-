"""TrafficMind local server: API routes plus the existing static dashboard."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api.routes import router
from backend.config import get_settings
from backend.database import init_db
from backend.services.jobs import interrupted_jobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    interrupted = interrupted_jobs()
    if interrupted:
        logger.warning("Marked %d interrupted processing jobs failed on startup", interrupted)
    yield


app = FastAPI(title="TrafficMind local API", version="0.1.0",
              description="Local traffic analytics API. Demo data is marked; YOLO is an optional local dependency.",
              lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                   allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "DELETE"],
                   allow_headers=["Content-Type"])
app.include_router(router)


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(settings.project_root / "index.html", media_type="text/html")


@app.get("/styles.css", include_in_schema=False)
def styles() -> FileResponse:
    return FileResponse(settings.project_root / "styles.css", media_type="text/css")


@app.get("/app.js", include_in_schema=False)
def frontend_script() -> FileResponse:
    return FileResponse(settings.project_root / "app.js", media_type="text/javascript")


@app.get("/api-client.js", include_in_schema=False)
def api_client_script() -> FileResponse:
    return FileResponse(settings.project_root / "api-client.js", media_type="text/javascript")


@app.get("/backend-ui.js", include_in_schema=False)
def backend_ui_script() -> FileResponse:
    return FileResponse(settings.project_root / "backend-ui.js", media_type="text/javascript")


app.mount("/assets", StaticFiles(directory=settings.project_root / "assets"), name="assets")

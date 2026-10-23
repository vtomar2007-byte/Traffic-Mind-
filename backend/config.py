"""Environment-backed configuration with safe local defaults."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _resolve_path(value: str | None, fallback: Path) -> Path:
    path = Path(value).expanduser() if value else fallback
    return (PROJECT_ROOT / path).resolve() if not path.is_absolute() else path.resolve()


@dataclass(frozen=True)
class Settings:
    project_root: Path
    data_dir: Path
    database_url: str
    model_path: Path | None
    max_upload_bytes: int
    max_video_frames: int
    process_every_n_frames: int
    confidence: float
    count_line_ratio: float
    cors_origins: tuple[str, ...]
    host: str
    port: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    data_dir = _resolve_path(os.getenv("TRAFFICMIND_DATA_DIR"), PROJECT_ROOT / "data")
    db_url = os.getenv("TRAFFICMIND_DATABASE_URL", "").strip()
    if not db_url:
        db_url = "sqlite:///" + (data_dir / "trafficmind.db").as_posix()
    model_value = os.getenv("TRAFFICMIND_MODEL_PATH", "").strip()
    default_model = PROJECT_ROOT / "models" / "trafficmind.pt"
    origins = tuple(x.strip() for x in os.getenv(
        "TRAFFICMIND_CORS_ORIGINS",
        "http://127.0.0.1:8000,http://localhost:8000,http://127.0.0.1:5500,http://localhost:5500",
    ).split(",") if x.strip())
    return Settings(
        project_root=PROJECT_ROOT,
        data_dir=data_dir,
        database_url=db_url,
        model_path=_resolve_path(model_value, default_model) if model_value else (default_model.resolve() if default_model.is_file() else None),
        max_upload_bytes=max(1, int(os.getenv("TRAFFICMIND_MAX_UPLOAD_MB", "150"))) * 1024 * 1024,
        max_video_frames=max(1, int(os.getenv("TRAFFICMIND_MAX_VIDEO_FRAMES", "3000"))),
        process_every_n_frames=max(1, int(os.getenv("TRAFFICMIND_PROCESS_EVERY_N_FRAMES", "2"))),
        confidence=min(1.0, max(0.01, float(os.getenv("TRAFFICMIND_CONFIDENCE", "0.35")))),
        count_line_ratio=min(0.95, max(0.05, float(os.getenv("TRAFFICMIND_COUNT_LINE_RATIO", "0.5")))),
        cors_origins=origins,
        host=os.getenv("TRAFFICMIND_HOST", "127.0.0.1"),
        port=int(os.getenv("TRAFFICMIND_PORT", "8000")),
    )

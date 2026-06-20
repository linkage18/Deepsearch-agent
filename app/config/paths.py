"""
Runtime path configuration.

All mutable runtime data is rooted under DATA_ROOT so local runs and Docker
deployments use the same directory layout.
"""

import os
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = PROJECT_ROOT / "app"


def _resolve_path(value: str | None, default: Path) -> Path:
    if not value:
        return default.resolve()
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


DATA_ROOT = _resolve_path(os.getenv("DATA_ROOT"), PROJECT_ROOT / "data")
UPLOAD_DIR = _resolve_path(os.getenv("UPLOAD_DIR"), DATA_ROOT / "uploads")
REPORT_DIR = _resolve_path(os.getenv("REPORT_DIR"), DATA_ROOT / "reports")
PAPER_DIR = _resolve_path(os.getenv("LLAMAINDEX_PAPER_DIR"), DATA_ROOT / "papers")
INDEX_DIR = _resolve_path(
    os.getenv("LLAMAINDEX_INDEX_DIR"),
    DATA_ROOT / "paper_index",
)
MODEL_CACHE_DIR = _resolve_path(os.getenv("MODEL_CACHE_DIR"), DATA_ROOT / "model_cache")
SESSIONS_DB_PATH = _resolve_path(
    os.getenv("SESSIONS_DB_PATH"),
    DATA_ROOT / "sessions.sqlite3",
)


def ensure_runtime_dirs() -> None:
    for path in (DATA_ROOT, UPLOAD_DIR, REPORT_DIR, PAPER_DIR, INDEX_DIR, MODEL_CACHE_DIR):
        path.mkdir(parents=True, exist_ok=True)
    _seed_paper_dir()


def _seed_paper_dir() -> None:
    legacy_dir = PROJECT_ROOT / "docs" / "papers"
    if not legacy_dir.exists() or any(PAPER_DIR.iterdir()):
        return
    for source in legacy_dir.rglob("*"):
        if not source.is_file():
            continue
        target = PAPER_DIR / source.relative_to(legacy_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

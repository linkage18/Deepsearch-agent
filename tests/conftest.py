"""
pytest configuration and shared fixtures.
"""

import os
import sys
from pathlib import Path

import pytest

# Ensure app is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Set test env vars BEFORE any module imports happen
os.environ.setdefault("DISABLE_API_AUTH", "true")
os.environ.setdefault("SEARXNG_BASE_URL", "http://localhost:9999")
os.environ.setdefault("MYSQL_HOST", "localhost")
os.environ.setdefault("MYSQL_USER", "test")
os.environ.setdefault("MYSQL_PASSWORD", "test")
os.environ.setdefault("MYSQL_DATABASE", "test_db")
os.environ.setdefault("AGENT_MAX_CONCURRENCY", "2")
os.environ.setdefault("AGENT_TASK_TIMEOUT_SECONDS", "10")
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "100")
os.environ.setdefault("DATA_ROOT", str(Path(__file__).resolve().parents[1] / "data"))


@pytest.fixture(autouse=True)
def verify_auth_disabled():
    """Ensure auth is disabled for all tests."""
    assert os.environ.get("DISABLE_API_AUTH") == "true"


@pytest.fixture
def tmp_db_path(tmp_path):
    """Return a temporary SQLite database path."""
    return tmp_path / "test_sessions.sqlite3"


@pytest.fixture
def isolated_session_store(tmp_db_path):
    """Provide an isolated session store backed by a temp SQLite file."""
    from app.models import session as session_store
    original = session_store.SESSION_DB_PATH
    session_store.set_session_db_path(tmp_db_path)
    yield session_store
    session_store.close_pool()
    session_store.set_session_db_path(original)


@pytest.fixture
def isolated_memory_store(tmp_db_path):
    """Provide an isolated memory store backed by a temp SQLite file."""
    from app.memory.memory_store import MemoryStore
    store = MemoryStore(tmp_db_path)
    yield store
    MemoryStore.close_pool()

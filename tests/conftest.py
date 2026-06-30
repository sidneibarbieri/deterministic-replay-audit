"""Shared fixtures - isolated SQLite per test that hits the REST API."""

from __future__ import annotations

import pytest
from sqlmodel import create_engine


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    """FastAPI TestClient with empty SQLite DB (no shared application DB)."""
    import arenawealth.models.database as db_mod

    db_file = tmp_path / "test_api.db"
    url = f"sqlite:///{db_file}"
    eng = create_engine(url, connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_mod, "engine", eng)
    monkeypatch.setattr(db_mod, "DATABASE_URL", url)

    from fastapi.testclient import TestClient

    from arenawealth.api.main import app

    with TestClient(app) as client:
        yield client

"""Shared pytest fixtures.

Every test runs against:
  * a throwaway SQLite file in a temp dir (never the dev DB),
  * only the ``mock`` provider (no network to real flight APIs),
  * a TestClient used as a context manager so startup/shutdown (table creation,
    FX warmup) actually run.

FX warmup will try to hit open.er-api.com; if the machine is offline the
service silently falls back to baked-in rates, so tests still pass.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def _test_env(tmp_path_factory):
    """Point the app at a temp DB + mock-only providers BEFORE it's imported."""
    db_file = tmp_path_factory.mktemp("db") / "test.sqlite3"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_file}"
    os.environ["ENABLED_PROVIDERS"] = "mock"
    os.environ["APP_ENV"] = "test"
    # Make sure any cached Settings created by an earlier import are dropped.
    from app.config import get_settings

    get_settings.cache_clear()
    yield


@pytest.fixture
def client():
    """A FastAPI TestClient with lifespan events run."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def future_dates():
    """(departure, return) ISO strings safely in the future."""
    from datetime import date, timedelta

    dep = date.today() + timedelta(days=30)
    ret = date.today() + timedelta(days=44)
    return dep.isoformat(), ret.isoformat()

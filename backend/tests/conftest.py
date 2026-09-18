"""Shared pytest setup for the backend test suite.

Sets an isolated, throwaway sqlite database *before* app.db creates its
engine, so integration tests never touch the real dev leadrank.db. This
module runs once, before any test module in this directory is imported.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_tmp_dir = tempfile.mkdtemp(prefix="leadrank_test_")
os.environ["LEADRANK_DATABASE_URL"] = f"sqlite:///{_tmp_dir}/test.db"
os.environ["LEADRANK_SCAN_MODE"] = "offline"
# A non-empty placeholder so /api/v1/runs/search is reachable in tests;
# SaaSquatchSource.fetch is mocked wherever it's exercised, so no real
# credential or network call is ever made.
os.environ.setdefault("LEADRANK_SAASQUATCH_API_KEY", "test-placeholder-key")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c

"""Shared fixtures for the dashboard test-suite (auto-loaded by pytest)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard_test_http import serve_dashboard  # noqa: E402


@pytest.fixture
def dashboard_server(tmp_path):
    """Serve the dashboard app from a blank tmp data dir (single shared copy)."""
    with serve_dashboard(tmp_path, config={"title": "Test Board"}) as (base, _tmp):
        yield base

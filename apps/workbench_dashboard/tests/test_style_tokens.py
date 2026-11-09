"""Dashboard style tokens stay the single source for app.css values."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CHECKER = ROOT / "scripts" / "check_style_tokens.py"
INDEX = ROOT / "apps" / "workbench_dashboard" / "web" / "index.html"


def test_style_tokens_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, str(CHECKER), "--check"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_tokens_stylesheet_loads_before_app_css() -> None:
    html = INDEX.read_text(encoding="utf-8")
    tokens_pos = html.find('<link rel="stylesheet" href="style-tokens.css">')
    app_pos = html.find('<link rel="stylesheet" href="app.css">')
    assert tokens_pos != -1 and app_pos != -1 and tokens_pos < app_pos

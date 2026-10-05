from __future__ import annotations

import tomllib
from pathlib import Path

from config import EXAMPLE_CONFIG_PATH, load_config

ROOT = Path(__file__).resolve().parents[1]


def test_default_council_config_stays_loadable() -> None:
    config = load_config(ROOT / EXAMPLE_CONFIG_PATH)

    assert len(config.members) >= 1
    for member in config.members:
        assert member.name
        assert member.model
        assert member.system_prompt


def test_documented_console_scripts_exist() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = pyproject["project"]["scripts"]

    assert scripts["local-ai-council"] == "main:main"
    assert scripts["local-ai-council-web"] == "web_app:main"


def test_web_ui_keeps_javascript_mount_points() -> None:
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

    for element_id in [
        "connectionStatus",
        "conversationInput",
        "promptForm",
        "promptInput",
        "askButton",
        "councilGrid",
    ]:
        assert f'id="{element_id}"' in html


def test_task_runner_keeps_core_operations() -> None:
    tasks = (ROOT / "tasks.ps1").read_text(encoding="utf-8")

    for task in [
        "init",
        "install",
        "pull-model",
        "start",
        "stop",
        "status",
        "cli",
        "list",
        "check",
    ]:
        assert f'"{task}"' in tasks


def test_private_runtime_files_are_gitignored_and_example_config_is_trackable() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "council.json" in gitignore.splitlines()
    assert "council.example.json" not in gitignore.splitlines()
    assert (ROOT / EXAMPLE_CONFIG_PATH).is_file()

    for pattern in ["data/", "logs/", "__pycache__/", ".pytest_cache/", ".idea/"]:
        assert pattern in gitignore

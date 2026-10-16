"""Directory discovery must respect depth and hidden boundaries while walking."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from ai_agent import ToolContext
from ai_agent.tools.filesystem import ListDirTool


def test_visible_output_order_depth_and_count_remain_compatible(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "child.txt").write_text("child")
    (tmp_path / "z.txt").write_text("root")
    tool, context = ListDirTool(), ToolContext(tmp_path)
    shallow = tool.execute({"max_depth": 1}, context)
    assert shallow.output.splitlines() == ["📁 a", "📄 z.txt"]
    assert shallow.metadata["count"] == 2
    default = tool.execute({}, context)
    assert default.output.splitlines() == ["📁 a", f"  📄 a{os.sep}child.txt", "📄 z.txt"]
    assert default.metadata == {"path": str(tmp_path.resolve()), "count": 3}


def test_depth_limit_does_not_scan_excluded_descendants(tmp_path, monkeypatch):
    deep = tmp_path / "visible" / "deeper"
    deep.mkdir(parents=True)
    (deep / "excluded.txt").write_text("irrelevant")
    (tmp_path / "visible" / "included.txt").write_text("visible")
    original_scan = os.scandir

    def guarded_scan(path):
        assert Path(path).resolve() != deep.resolve(), "Scanned beyond requested depth"
        return original_scan(path)

    monkeypatch.setattr(os, "scandir", guarded_scan)
    result = ListDirTool().execute({"max_depth": 2}, ToolContext(tmp_path))
    assert result.output.splitlines() == [
        "📁 visible",
        "  📁 visible/deeper".replace("/", os.sep),
        "  📄 visible/included.txt".replace("/", os.sep),
    ]
    assert result.metadata == {"path": str(tmp_path.resolve()), "count": 3}


def test_hidden_directories_are_not_scanned(tmp_path, monkeypatch):
    for name in (".git", "__pycache__"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "private.txt").write_text("irrelevant")
    (tmp_path / "visible.txt").write_text("visible")
    original_scan = os.scandir

    def guarded_scan(path):
        assert Path(path).name not in {".git", "__pycache__"}, "Scanned hidden directory"
        return original_scan(path)

    monkeypatch.setattr(os, "scandir", guarded_scan)
    result = ListDirTool().execute({}, ToolContext(tmp_path))
    assert result.output == "📄 visible.txt"
    assert result.metadata["count"] == 1


def test_selected_workspace_under_hidden_ancestor_lists_visible_contents(tmp_path):
    workspace = tmp_path / ".owner" / "project"
    workspace.mkdir(parents=True)
    (workspace / "visible.py").write_text("pass")
    result = ListDirTool().execute({}, ToolContext(workspace))
    assert result.output == "📄 visible.py"
    assert result.metadata["count"] == 1


def test_zero_depth_does_not_scan_directory(tmp_path, monkeypatch):
    (tmp_path / "visible.txt").write_text("visible")

    def forbidden_scan(path):
        raise AssertionError("Depth zero must not scan entries")

    monkeypatch.setattr(os, "scandir", forbidden_scan)
    result = ListDirTool().execute({"max_depth": 0}, ToolContext(tmp_path))
    assert result.output == "(empty directory)"
    assert result.metadata["count"] == 0


def test_internal_directory_link_is_not_traversed(tmp_path, monkeypatch):
    target = tmp_path / "real"
    target.mkdir()
    (target / "child.txt").write_text("visible")
    link = tmp_path / "alias"
    if os.name == "nt":
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "New-Item -ItemType Junction -Path $env:TEST_LINK "
                "-Target $env:TEST_TARGET | Out-Null",
            ],
            env={**os.environ, "TEST_LINK": str(link), "TEST_TARGET": str(target)},
            check=True,
        )
    else:
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError as error:
            pytest.skip(f"Directory links unavailable: {error}")
    original_scan = os.scandir

    def guarded_scan(path):
        assert Path(path) != link, "Traversed directory link"
        return original_scan(path)

    try:
        monkeypatch.setattr(os, "scandir", guarded_scan)
        result = ListDirTool().execute({"max_depth": 3}, ToolContext(tmp_path))
        assert f"real{os.sep}child.txt" in result.output
        assert f"alias{os.sep}child.txt" not in result.output
    finally:
        if os.name == "nt":
            link.rmdir()
        else:
            link.unlink()

"""A match limit should stop discovery as well as content scanning."""

import ai_agent.tools.search as search_tools
from ai_agent import GrepSearchTool, ToolCall, ToolContext


def test_grep_stops_discovery_at_first_sufficient_file(tmp_path, monkeypatch):
    first = tmp_path / "first.txt"
    later = tmp_path / "later.txt"
    first.write_text("needle\n", encoding="utf-8")
    later.write_text("needle\n", encoding="utf-8")
    visited = []

    def entries(base, context):
        for path in (first, later):
            visited.append(path.name)
            yield path

    monkeypatch.setattr(search_tools, "_workspace_entries", entries)
    result = GrepSearchTool().run(
        ToolCall("grep_search", {"query": "needle", "max_matches": 1}), ToolContext(tmp_path)
    )
    assert not result.is_error
    assert result.output == "first.txt:1: needle"
    assert result.metadata == {"query": "needle", "matches": 1}
    assert visited == ["first.txt"]


def test_grep_skips_directories_and_nonmatches_before_limit(tmp_path, monkeypatch):
    first = tmp_path / "first.txt"
    directory = tmp_path / "folder"
    match = tmp_path / "match.txt"
    later = tmp_path / "later.txt"
    first.write_text("nothing\n", encoding="utf-8")
    directory.mkdir()
    match.write_text("needle\nneedle\n", encoding="utf-8")
    later.write_text("needle\n", encoding="utf-8")
    visited = []
    read_paths = []
    original_read_text = type(tmp_path).read_text

    def read_text(path, *args, **kwargs):
        read_paths.append(path.name)
        return original_read_text(path, *args, **kwargs)

    def entries(base, context):
        for path in (first, directory, match, later):
            visited.append(path.name)
            yield path

    monkeypatch.setattr(search_tools, "_workspace_entries", entries)
    monkeypatch.setattr(type(tmp_path), "read_text", read_text)
    result = GrepSearchTool().run(
        ToolCall("grep_search", {"query": "needle", "max_matches": 1}), ToolContext(tmp_path)
    )
    assert not result.is_error
    assert result.output == "match.txt:1: needle"
    assert visited == ["first.txt", "folder", "match.txt"]
    assert read_paths == ["first.txt", "match.txt"]


def test_grep_explicit_file_does_not_walk(tmp_path, monkeypatch):
    target = tmp_path / "chosen.txt"
    target.write_text("needle\n", encoding="utf-8")

    def unexpected_walk(base, context):
        raise AssertionError("An explicit file must not enumerate the workspace")

    monkeypatch.setattr(search_tools, "_workspace_entries", unexpected_walk)
    result = GrepSearchTool().run(
        ToolCall("grep_search", {"query": "needle", "path": "chosen.txt"}), ToolContext(tmp_path)
    )
    assert not result.is_error
    assert result.output == "chosen.txt:1: needle"

"""Context limits and references to supplied source lines, without model calls."""

from pathlib import Path

import pytest
from ai_agent.delegation_context import assemble_delegation_context, has_source_citation
from ai_provider.repo_context import RepoContextFile


def _file(content: str, source: str = "src.py") -> RepoContextFile:
    return RepoContextFile(Path(source), source, content, inside_repo=True)


@pytest.mark.parametrize("budget", [1, 10, 22, 30, 50, 70, 100, 120, 500])
def test_total_budget_includes_every_separator_header_and_marker(budget: int):
    files = (_file("first\nsecond\nthird"), _file("another\nfile", "other.py"))
    context = assemble_delegation_context(files, max_chars=budget)
    assert len(context.text) <= budget
    for source, count in context.source_line_counts:
        assert count > 0
        assert has_source_citation(f"[source:{source}:{count}]", context)
        assert not has_source_citation(f"[source:{source}:{count + 1}]", context)


def test_context_without_content_has_no_citable_sources():
    context = assemble_delegation_context((_file(""),), max_chars=500)
    assert context.sources == ()
    assert not has_source_citation("[source:src.py:1]", context)


def test_fitting_final_line_does_not_reserve_an_unneeded_truncation_marker():
    text = "=== SOURCE: src.py ===\n1: first\n2: second"
    context = assemble_delegation_context((_file("first\nsecond"),), max_chars=len(text))
    assert context.text == text
    assert context.source_line_counts == (("src.py", 2),)


@pytest.mark.parametrize(
    "citation",
    [
        "[source:src.py:",
        "[source:src.py:1",
        "[source:src.py:0]",
        "[source:src.py:-1]",
        "[source:src.py:1.5]",
        "[source:src.py:999]",
        "[source:wrong.py:1]",
        "[source:src.py:one]",
        "no reference",
        "[source:src.py:" + "9" * 5000 + "]",
    ],
)
def test_incomplete_fabricated_and_out_of_range_references_are_rejected(citation: str):
    context = assemble_delegation_context((_file("first\nsecond"),), max_chars=500)
    assert not has_source_citation(citation, context)


def test_path_separators_and_existing_case_insensitive_matching_are_preserved():
    context = assemble_delegation_context((_file("first", "Src/example.py"),), max_chars=500)
    assert has_source_citation(r"Fact [source:src\EXAMPLE.py:1]", context)


def test_windows_absolute_source_path_is_not_confused_with_line_separator():
    context = assemble_delegation_context((_file("first", "C:/repo/src.py"),), max_chars=500)
    assert has_source_citation("[source:C:/repo/src.py:1]", context)


def test_truncated_lines_cannot_be_cited_as_if_supplied():
    context = assemble_delegation_context((_file("short\n" + "x" * 500),), max_chars=80)
    assert context.source_line_counts == (("src.py", 1),)
    assert "[source truncated after line 1]" in context.text
    assert has_source_citation("[source:src.py:1]", context)
    assert not has_source_citation("[source:src.py:2]", context)


@pytest.mark.parametrize("budget", [0, -1])
def test_invalid_budget_is_rejected(budget: int):
    with pytest.raises(ValueError, match="greater than zero"):
        assemble_delegation_context((_file("first"),), max_chars=budget)

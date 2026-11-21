"""Document status ledger covers every top-level doc and plan."""

from __future__ import annotations

import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs" / "document-status.md"
REGISTRY = ROOT / "docs" / "goals" / "registry.json"
STATUSES = {"ACTED", "KNOWLEDGE", "PENDING", "IGNORE", "TRIAGE"}
PLAN_STATUSES = {"draft", "active", "blocked", "done", "dropped"}
HEADER_RE = re.compile(
    r"<!-- Project: ([^|]+) \| Status: ([^|]+) \| Timebox: ([^|]*) \| Replaces: (.+) -->"
)


def _ledger_rows() -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"\| (docs/\S+) \| ([A-Z]+) \| .* \|", line.strip())
        if match:
            rows[match.group(1)] = match.group(2)
    return rows


def test_ledger_covers_top_level_docs_and_plans() -> None:
    rows = _ledger_rows()
    assert rows, "ledger has no parseable rows"
    assert set(rows.values()) <= STATUSES
    expected = {
        path.relative_to(ROOT).as_posix()
        for pattern in ("docs/*.md", "docs/plans/*.md", "docs/plans/*.txt", "docs/plans/*.docx")
        for path in ROOT.glob(pattern)
    } - {
        "docs/document-status.md",
        # Live session plan: rewritten every window, covered by its header gate.
        "docs/plans/unattended-work-plan.md",
    }
    assert expected, "no documents found"
    missing = sorted(expected - set(rows))
    assert not missing, f"ledger missing rows: {missing}"
    for document in sorted(expected):
        assert rows[document] in STATUSES, document


def _check_ledger_paths(root: pathlib.Path, rows: dict[str, str]) -> None:
    for document, status in sorted(rows.items()):
        # These ignored assets are not part of the public checkout. A local
        # private tree, when installed, still has to satisfy its ledger rows.
        if (
            document in {"docs/api-reference/", "docs/artifacts/"}
            and not (root / document).exists()
        ):
            continue
        if document == "docs/pycharm-ai-prompt-library.md" and not (root / document).exists():
            continue
        if any(
            document.startswith(tree + "/") and not (root / tree).exists()
            for tree in ("docs/plans", "docs/library-private")
        ):
            continue
        if document.endswith("/"):
            assert (root / document).is_dir(), document
        else:
            assert (root / document).is_file(), (document, status)


def test_ledger_paths_exist() -> None:
    _check_ledger_paths(ROOT, _ledger_rows())


def _registry_ids() -> set[str]:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return set(registry["projects"])


def _plan_header(path: pathlib.Path) -> re.Match[str] | None:
    for line in path.read_text(encoding="utf-8").splitlines()[:5]:
        match = HEADER_RE.fullmatch(line.strip())
        if match:
            return match
    return None


def test_registry_goals_exist() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert registry["version"] == 1
    for project_id, entry in sorted(registry["projects"].items()):
        assert (ROOT / entry["goal"]).is_file(), project_id
        assert entry["repo"], project_id
        assert entry["owner"], project_id
        assert entry["health"] in {"on-track", "at-risk", "off-track", "paused"}, project_id
        for relation, targets in entry.get("relations", {}).items():
            for target in targets:
                assert target in registry["projects"], (project_id, relation, target)


def _check_plan_headers(root: pathlib.Path, known: set[str]) -> None:
    plans = sorted((root / "docs" / "plans").glob("*.md"))
    assert plans, "no local plans found"
    for path in plans:
        match = _plan_header(path)
        assert match, f"{path.name}: missing plan header"
        projects = [item.strip() for item in match.group(1).split(",")]
        assert projects and all(item in known for item in projects), (
            f"{path.name}: unknown project in {projects}"
        )
        assert match.group(2).strip() in PLAN_STATUSES, f"{path.name}: bad status"
        assert match.group(3).strip(), f"{path.name}: empty timebox"
        replaces = match.group(4).strip()
        if replaces != "none":
            for item in (part.strip() for part in replaces.split(",")):
                assert (root / item).exists(), f"{path.name}: replaces missing {item}"


def test_local_plans_carry_valid_headers() -> None:
    if not (ROOT / "docs" / "plans").exists():
        pytest.skip("private docs/plans tree is not installed")
    _check_plan_headers(ROOT, _registry_ids())


@pytest.mark.parametrize(
    ("header", "error"),
    [
        ("<!-- Project: fixture | Status: active | Timebox: one day | Replaces: none -->", None),
        (
            "<!-- Project: fixture | Status: done | Timebox: one day | Replaces: docs/old-plan.md -->",
            None,
        ),
        ("", "missing plan header"),
        (
            "<!-- Project: unknown | Status: active | Timebox: one day | Replaces: none -->",
            "unknown project",
        ),
        (
            "<!-- Project: fixture | Status: wrong | Timebox: one day | Replaces: none -->",
            "bad status",
        ),
        (
            "<!-- Project: fixture | Status: active | Timebox:  | Replaces: none -->",
            "empty timebox",
        ),
        (
            "<!-- Project: fixture | Status: active | Timebox: one day | Replaces: docs/missing.md -->",
            "replaces missing",
        ),
    ],
)
def test_plan_header_contract(tmp_path: pathlib.Path, header: str, error: str | None) -> None:
    plans = tmp_path / "docs" / "plans"
    plans.mkdir(parents=True)
    (plans / "example.md").write_text(header + "\n# Synthetic plan\n", encoding="utf-8")
    (tmp_path / "docs" / "old-plan.md").touch()
    if error:
        with pytest.raises(AssertionError, match=error):
            _check_plan_headers(tmp_path, {"fixture"})
    else:
        _check_plan_headers(tmp_path, {"fixture"})


def test_empty_installed_plan_tree_fails(tmp_path: pathlib.Path) -> None:
    (tmp_path / "docs" / "plans").mkdir(parents=True)
    with pytest.raises(AssertionError, match="no local plans found"):
        _check_plan_headers(tmp_path, {"fixture"})


def test_local_plan_gate_checks_installed_tree(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    with pytest.raises(pytest.skip.Exception, match="not installed"):
        test_local_plans_carry_valid_headers()
    plans = tmp_path / "docs" / "plans"
    plans.mkdir(parents=True)
    with pytest.raises(AssertionError, match="no local plans found"):
        test_local_plans_carry_valid_headers()
    plan = plans / "example.md"
    plan.write_text("# Missing header\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="missing plan header"):
        test_local_plans_carry_valid_headers()
    project = sorted(_registry_ids())[0]
    plan.write_text(
        f"<!-- Project: {project} | Status: active | Timebox: one day | Replaces: none -->\n",
        encoding="utf-8",
    )
    test_local_plans_carry_valid_headers()


def test_ledger_public_and_local_contract(tmp_path: pathlib.Path) -> None:
    rows = dict.fromkeys(
        [
            "docs/api-reference/",
            "docs/artifacts/",
            "docs/plans/example.md",
            "docs/library-private/",
            "docs/pycharm-ai-prompt-library.md",
        ],
        "KNOWLEDGE",
    )
    _check_ledger_paths(tmp_path, rows)
    with pytest.raises(AssertionError, match="public.md"):
        _check_ledger_paths(tmp_path, {"docs/public.md": "KNOWLEDGE"})
    plans = tmp_path / "docs" / "plans"
    plans.mkdir(parents=True)
    with pytest.raises(AssertionError, match="example.md"):
        _check_ledger_paths(tmp_path, rows)
    (plans / "example.md").touch()
    _check_ledger_paths(tmp_path, rows)
    (tmp_path / "docs" / "api-reference").touch()
    with pytest.raises(AssertionError, match="api-reference"):
        _check_ledger_paths(tmp_path, rows)

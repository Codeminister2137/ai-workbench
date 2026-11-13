"""Document status ledger covers every top-level doc and plan."""

from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs" / "document-status.md"
REGISTRY = ROOT / "docs" / "goals" / "registry.json"
STATUSES = {"ACTED", "KNOWLEDGE", "PENDING", "IGNORE", "TRIAGE"}
PLAN_STATUSES = {"draft", "active", "blocked", "done", "dropped"}
HEADER_RE = re.compile(
    r"<!-- Project: ([^|]+) \| Status: ([^|]+) \| Timebox: ([^|]+) \| Replaces: ([^-]+) -->"
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


def test_ledger_paths_exist() -> None:
    rows = _ledger_rows()
    for document, status in sorted(rows.items()):
        if document.endswith("/"):
            assert (ROOT / document).is_dir(), document
        else:
            assert (ROOT / document).is_file(), (document, status)


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


def test_plans_carry_valid_headers() -> None:
    plans = sorted((ROOT / "docs" / "plans").glob("*.md"))
    assert plans, "no local plans found"
    known = _registry_ids()
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
                assert (ROOT / item).exists(), f"{path.name}: replaces missing {item}"

"""Document status ledger covers every top-level doc and plan."""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs" / "document-status.md"
STATUSES = {"ACTED", "KNOWLEDGE", "PENDING", "IGNORE", "TRIAGE"}


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
    } - {"docs/document-status.md"}
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

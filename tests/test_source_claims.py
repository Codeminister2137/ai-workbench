"""Tests for the deterministic L1 claim extractor."""

from __future__ import annotations

from pathlib import Path

from ai_provider.source_claims import extract_claims

FIXTURE = """\
- **opencode-go** (`GET opencode.ai/zen/go/v1/usage`): rolling windows.
  Live-probed 2026-11-17: 403 Forbidden with our key.
Owner 11-17: Extra Usage is OFF.
"""


def test_provider_bullet_and_endpoint(tmp_path: Path) -> None:
    doc = tmp_path / "source.md"
    doc.write_text(FIXTURE, encoding="utf-8")
    claims = extract_claims(doc)
    providers = [c for c in claims if c.kind == "provider_finding"]
    assert [(c.provider, c.line) for c in providers] == [("opencode-go", 1)]
    endpoints = [c for c in claims if c.kind == "endpoint"]
    assert [c.text for c in endpoints] == ["opencode.ai/zen/go/v1/usage"]
    assert endpoints[0].provider == "opencode-go"


def test_dated_finding_and_owner_note(tmp_path: Path) -> None:
    doc = tmp_path / "source.md"
    doc.write_text(FIXTURE, encoding="utf-8")
    claims = extract_claims(doc)
    dated = [c for c in claims if c.kind == "dated_finding"]
    assert len(dated) == 1
    assert dated[0].text.startswith("2026-11-17:")
    assert dated[0].provider == "opencode-go"
    owner = [c for c in claims if c.kind == "owner_note"]
    assert len(owner) == 1
    assert owner[0].line == 3


def test_real_source_state_has_cited_claims() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "packages"
        / "ai_provider"
        / "docs"
        / "source-state.md"
    )
    claims = extract_claims(path)
    assert len(claims) > 20
    assert {c.provider for c in claims if c.kind == "provider_finding"} >= {"opencode-go"}
    assert all(c.file == str(path) and c.line >= 1 for c in claims)

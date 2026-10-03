"""Offline acceptance tests for the disposable research-report contract."""

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate_research_report.py"
_SPEC = importlib.util.spec_from_file_location("validate_research_report", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
validator = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = validator
_SPEC.loader.exec_module(validator)
_TODAY = date(2026, 10, 1)
_SOURCE = "S1 https://docs.python.org/3/ accessed 2026-09-30; fetched"


def report(*, source=_SOURCE, candidate="Verified: documented language behavior [S1]."):
    bodies = (
        "A synthetic report used for structural tests. " * 170,
        source,
        candidate,
        "Compare task quality and operational constraints.",
        "Provider-specific capabilities need independent confirmation.",
        "Unknowns: actual account entitlements and live performance remain unverified.",
        "Inspect the documented source before changing code.",
        "Offline structural validation executed; no network or inference requested.",
    )
    return "\n\n".join(
        f"## {index}. {name}\n\n{body}"
        for index, (name, body) in enumerate(
            zip(validator.REQUIRED_SECTIONS, bodies, strict=True), 1
        )
    )


def errors(text):
    return validator.validate_report(text, today=_TODAY)


def test_complete_report_passes_without_network():
    assert errors(report()) == []


def test_typographic_heading_hyphens_and_thematic_breaks_are_accepted():
    text = (
        report()
        .replace("source-specific", "source\u2011specific")
        .replace("stale-data", "stale\u2011data")
    )
    text = text.replace("## 4.", "---\n\n## 4.")
    assert errors(text) == []


@pytest.mark.parametrize(
    "source",
    [
        "- " + _SOURCE,
        "### S1\nhttps://docs.python.org/3/\nAccessed: 2026-09-30\nRetrieval: fetched",
        "| ID | URL | Accessed | Retrieval |\n| --- | --- | --- | --- |\n"
        "| S1 | https://docs.python.org/3/ | 2026-09-30 | fetched |",
        "- S1\n  URL: https://docs.python.org/3/\n  Accessed: 2026-09-30\n  Retrieval: fetched",
    ],
)
def test_source_map_accepts_common_markdown_shapes(source):
    assert errors(report(source=source)) == []


def test_direct_url_citation_does_not_require_source_ids():
    assert (
        errors(
            report(
                source=_SOURCE.replace("S1 ", ""),
                candidate="Inferred: hypothesis https://docs.python.org/3/.",
            )
        )
        == []
    )


@pytest.mark.parametrize("marker", ["1.", "1)"])
def test_numbered_candidates_are_checked_individually(marker):
    candidate = f"{marker} Verified: supported fact [S1].\n2. Inferred: missing citation."
    result = errors(report(candidate=candidate))
    assert any("candidate entry 2: cite" in error for error in result)
    assert errors(report(candidate=candidate + " [S1]")) == []


def test_unknown_numbered_candidate_cannot_hide_uncited_verified_neighbor():
    result = errors(report(candidate="1. Unknown: unassessed.\n2. Verified: uncited claim."))
    assert any("candidate entry 2: cite" in error for error in result)
    assert any("candidate entry 2: verified claims" in error for error in result)


def test_numbered_sources_preserve_independent_provenance():
    source = "1. " + _SOURCE + "\n2. S2 https://example.org/; not fetched; not accessed"
    assert errors(report(source=source)) == []


def test_not_fetched_source_and_unknown_claim_are_honest_and_valid():
    assert (
        errors(
            report(
                source="S1 https://docs.python.org/3/; not fetched; not accessed",
                candidate="Unknown: account support requires investigation.",
            )
        )
        == []
    )


@pytest.mark.parametrize("section", validator.REQUIRED_SECTIONS)
def test_each_promised_section_is_required(section):
    text = report()
    # Remove a heading, retaining its words in prose, to reproduce substring false positives.
    text = text.replace(
        f"## {validator.REQUIRED_SECTIONS.index(section) + 1}. {section}",
        f"Mention of {section} in body text",
    )
    assert f"missing required section: {section}" in errors(text)


def test_empty_section_is_rejected():
    text = report().replace("Compare task quality and operational constraints.", "")
    assert "empty required section: Recommended fields, metrics, or decision criteria" in errors(
        text
    )


def test_duplicate_section_is_rejected():
    assert "duplicate section: Source map" in errors(report() + "\n## Source map\n" + _SOURCE)


def test_source_free_report_fails_even_when_long_and_all_headings_exist():
    result = errors(
        report(source="No sources gathered.", candidate="Unknown: no facts established.")
    )
    assert any("declare at least one" in error for error in result)


@pytest.mark.parametrize(
    "source,message",
    [
        (_SOURCE.replace("2026-09-30", ""), "missing access date"),
        (_SOURCE.replace("2026-09-30", "2026-02-30"), "invalid date"),
        (_SOURCE.replace("2026-09-30", "2026-10-02"), "in the future"),
        (_SOURCE.replace("; fetched", ""), "declare retrieval"),
        (_SOURCE.replace("https://docs.python.org/3/", "https://"), "malformed URL"),
        (
            _SOURCE.replace("https://docs.python.org/3/", "https://user:secret@example.org"),
            "malformed URL",
        ),
        ("S1 accessed 2026-09-30; fetched", "missing HTTP(S) URL"),
    ],
)
def test_source_provenance_errors_are_actionable(source, message):
    assert any(message in error for error in errors(report(source=source)))


def test_source_ids_cannot_ambiguously_refer_to_multiple_entries():
    source = "- " + _SOURCE + "\n- " + _SOURCE.replace("docs.python.org", "www.python.org")
    assert "source map: source IDs must be unique" in errors(report(source=source))


@pytest.mark.parametrize(
    "candidate,message",
    [
        ("Verified: fact [S2].", "citation [S2]: not declared"),
        ("Inferred: fact https://www.python.org/.", "citation URL not declared"),
        ("Claim without confidence label [S1].", "label confidence"),
        ("Inferred: uncited speculation.", "cite a declared URL"),
    ],
)
def test_claim_citation_and_confidence_errors(candidate, message):
    assert any(message in error for error in errors(report(candidate=candidate)))


def test_verified_claim_cannot_use_only_unfetched_sources():
    result = errors(report(source="S1 https://docs.python.org/3/; not fetched"))
    assert any("verified claims need" in error for error in result)


def test_each_candidate_table_row_needs_evidence():
    candidate = (
        "| Candidate | Confidence | Sources |\n| --- | --- | --- |\n"
        "| Language | verified | [S1] |\n| Undocumented feature | inferred | none |"
    )
    assert any("candidate entry 2: cite" in error for error in errors(report(candidate=candidate)))


def test_candidate_table_does_not_hide_uncited_list_entries():
    candidate = (
        "| Candidate | Confidence | Sources |\n| --- | --- | --- |\n"
        "| Language | verified | [S1] |\n\n- Inferred: unsupported extra candidate."
    )
    assert any("candidate entry 2: cite" in error for error in errors(report(candidate=candidate)))


def test_example_code_cannot_hide_length_advisory():
    text = report().replace(
        "A synthetic report used for structural tests. " * 170,
        "Short summary.\n```text\n" + "padding " * 1000 + "\n```",
    )
    advisories = []
    assert validator.validate_report(text, today=_TODAY, advisories=advisories) == []
    assert len(advisories) == 1
    assert "length advisory" in advisories[0]


def test_explicit_uncertainty_required_in_risks_section():
    text = report().replace(
        "Unknowns: actual account entitlements and live performance remain unverified.",
        "All products are suitable.",
    )
    assert any("explicitly state unknowns" in error for error in errors(text))


def test_headings_and_sources_in_code_or_comments_are_not_evidence():
    for text in (f"```markdown\n{report()}\n```", f"<!-- {report()} -->"):
        assert any("missing required section" in error for error in errors(text))


def test_short_complete_report_passes_with_optional_length_advisory():
    text = report().replace(
        "A synthetic report used for structural tests. " * 170, "Short summary."
    )
    assert errors(text) == []
    advisories = []
    assert validator.validate_report(text, today=_TODAY, advisories=advisories) == []
    assert len(advisories) == 1
    assert "does not fail completion or require repair" in advisories[0]


def test_cli_length_guideline_changes_advice_without_failing_completion(tmp_path, capsys):
    path = tmp_path / "short.md"
    path.write_text(
        report().replace("A synthetic report used for structural tests. " * 170, "Summary.")
    )
    assert validator.main([str(path)]) == 0
    assert "length advisory" in capsys.readouterr().err
    assert validator.main([str(path), "--min-chars", "1"]) == 0
    assert capsys.readouterr().err == ""


def test_cli_returns_nonzero_and_reports_missing_file(tmp_path, capsys):
    assert validator.main([str(tmp_path / "missing.md")]) == 1
    assert "missing research file" in capsys.readouterr().err


@pytest.mark.parametrize("content", [b"\xff\xfe\x00", None])
def test_cli_reports_unreadable_file_or_directory(tmp_path, capsys, content):
    path = tmp_path / "report.md"
    if content is None:
        path.mkdir()
    else:
        path.write_bytes(content)
    assert validator.main([str(path)]) == 1
    assert "cannot read research file" in capsys.readouterr().err


def test_cli_accepts_bom_and_paths_with_spaces(tmp_path, capsys):
    path = tmp_path / "research report.md"
    path.write_text(report(), encoding="utf-8-sig")
    assert validator.main([str(path)]) == 0
    assert "source retrieval/truth not verified" in capsys.readouterr().out


def test_cli_reports_multiple_failures_for_repair(tmp_path, capsys):
    path = tmp_path / "report.md"
    path.write_text("Executive summary\nSource map\nRepair checks performed")
    assert validator.main([str(path)]) == 1
    output = capsys.readouterr().err
    assert (
        "length advisory" in output
        and "missing required section" in output
        and "source map" in output
    )


def test_cli_rejects_invalid_threshold(tmp_path):
    with pytest.raises(SystemExit) as error:
        validator.main([str(tmp_path / "report.md"), "--min-chars", "0"])
    assert error.value.code == 2

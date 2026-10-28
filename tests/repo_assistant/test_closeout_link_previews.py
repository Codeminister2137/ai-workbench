"""Protected host regressions for complete links and bounded previews."""

import pytest
from ai_provider.closeout import format_cli_closeout


def render(raw):
    output = format_cli_closeout(response_text=raw, status="ready", execution_status="completed")
    preview = next(line for line in output.splitlines() if line.startswith("- Changed:"))
    assert "### Agent report\n" + raw in output
    prefix = "- Changed: Agent-reported outcome: "
    suffix = " (workspace changes are not independently attributed by the CLI)."
    return preview.removeprefix(prefix).removesuffix(suffix)


@pytest.mark.parametrize(
    "raw",
    [
        "Reviewed [assessment](/C:/Users/Example/" + ("long-segment/" * 25) + "assessment.md).",
        "Reviewed [assessment](</C:/Users/Example/"
        + ("space directory/" * 25)
        + "assessment.md>).",
        "Reviewed ![image](/C:/Users/Example/" + ("long-segment/" * 25) + "plot.png).",
        "Reviewed [assessment](/C:/Users/Example/" + ("nested(segment)/" * 25) + "assessment.md).",
    ],
)
def test_long_link_preview_never_cuts_destination_and_raw_report_stays_complete(raw):
    preview = render(raw)
    assert len(preview) <= 200
    assert "](" not in preview, "A long link cannot fit this bounded preview; use readable text."
    assert preview.strip() and not preview.startswith("...")


def test_short_link_keeps_existing_preview():
    raw = "Reviewed [assessment](/tmp/assessment.md)."
    assert render(raw) == raw


def test_long_plain_text_remains_bounded():
    raw = "Validated " + ("ordinary text " * 30).rstrip()
    preview = render(raw)
    assert len(preview) <= 200 and preview.endswith("...")


@pytest.mark.parametrize(
    "raw",
    [
        r"Reviewed [assess\]ment](/C:/Example/" + ("long/" * 50) + "report.md).",
        r"Reviewed [assessment](</C:/Example/" + ("parenthesis(" * 25) + "report.md>).",
        r"Reviewed [assessment](/C:/Example/" + (r"escaped\(name/" * 25) + "report.md).",
    ],
)
def test_valid_link_syntax_is_not_cut(raw):
    output = format_cli_closeout(response_text=raw, status="ready", execution_status="completed")
    preview = next(line for line in output.splitlines() if line.startswith("- Changed:"))
    assert "](" not in preview
    assert "### Agent report\n" + raw in output


def test_changed_prefix_with_long_link_stays_bounded_and_report_is_intact():
    raw = "- Changed: Reviewed [configuration](/C:/Example/" + ("deep/" * 50) + "config.toml)."
    assert render(raw) == "See the agent report below for the linked outcome."


def test_complete_short_link_before_long_tail_is_not_split():
    raw = "Reviewed [report](/tmp/report.md). " + ("details " * 40).rstrip()
    preview = render(raw)
    assert len(preview) <= 200 and "](" not in preview

"""Host regressions for full and collapsed reference-link previews."""

import pytest
from ai_provider.closeout import format_cli_closeout


@pytest.mark.parametrize(
    "usage,definition",
    [
        ("[" + "label-" * 40 + "][ref]", "[ref]: /C:/Example/report.md"),
        ("[report][" + "id-" * 80 + "]", "[" + "id-" * 80 + "]: /C:/Example/report.md"),
        ("[" + "label-" * 40 + "][]", "[" + "label-" * 40 + "]: /C:/Example/report.md"),
        ("![" + "image-" * 40 + "][ref]", "[ref]: /C:/Example/image.png"),
    ],
)
def test_long_reference_preview_is_bounded_and_complete_report_is_retained(usage, definition):
    raw = f"Reviewed {usage}.\n\n{definition}"
    output = format_cli_closeout(response_text=raw, status="ready", execution_status="completed")
    preview = next(line for line in output.splitlines() if line.startswith("- Changed:"))
    assert "See the agent report below for the linked outcome." in preview
    assert "### Agent report\n" + raw in output


def test_short_reference_preview_is_retained():
    raw = "Reviewed [report][ref].\n\n[ref]: /C:/Example/report.md"
    output = format_cli_closeout(response_text=raw, status="ready", execution_status="completed")
    assert "Agent-reported outcome: Reviewed [report][ref]. " in output
    assert "### Agent report\n" + raw in output


def test_bracketed_plain_text_keeps_existing_truncation():
    raw = "Validated [" + "ordinary text " * 30 + "]"
    output = format_cli_closeout(response_text=raw, status="ready", execution_status="completed")
    preview = next(line for line in output.splitlines() if line.startswith("- Changed:"))
    assert "... (workspace" in preview
    assert "See the agent report below" not in preview

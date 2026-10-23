"""Scripted review controls exercise final delivery after real local validation."""

from dataclasses import replace
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from ai_provider import (
    AIMessage,
    AIResponse,
    BackendInfo,
    BackendLocation,
    MessageRole,
    ProviderError,
)
from ai_provider.acceptance_processes import process_identity
from ai_provider.closeout import AUXILIARY_RESPONSE_NOTICE
from ai_provider.orchestrated_runs import SQLiteOrchestratedRunStore

from .support import _EXAMPLE, main


@pytest.mark.parametrize(
    "review", ["needs_revision", "bold_needs_revision", "fail", "pass", "invalid", "unavailable"]
)
@pytest.mark.parametrize("mode", ["implement", "coding-chat"])
@pytest.mark.parametrize("scrutiny_policy", ["advisory", "required"])
def test_native_final_delivery_preserves_draft_and_actual_validation(
    review: str, mode: str, scrutiny_policy: str, capsys, monkeypatch, tmp_path: Path
) -> None:
    """A scripted pass is a negative control, not evidence of semantic detection."""
    draft = "I independently verified the supplied hash."
    auxiliary_claim = "SYNTHETIC auxiliary claim: edits and all tests completed."
    revision = "The supplied hash remains unverified."
    issue = "No hash verification was observed."
    validator = (
        "import os\nfrom pathlib import Path\n"
        "Path('validation.pid').write_text(str(os.getpid()))\n"
        "assert 2 + 2 == 4\nprint('actual validation passed')\n"
    )
    (tmp_path / "validate.py").write_text(validator, encoding="utf-8")
    (tmp_path / "user-config.toml").write_text("", encoding="utf-8")
    catalog = _EXAMPLE.load_model_catalog(
        Path("packages/ai_orchestrator/examples/model_catalog.toml")
    )
    prepared = _EXAMPLE.run_coding_prompt(
        "Scripted offline delivery control.",
        _EXAMPLE.coding_task_profile(model_override="gpt-oss:20b"),
        catalog,
    )
    prepared = replace(
        prepared, config=_EXAMPLE.BackendConfig(_EXAMPLE.ProviderKind.OLLAMA, "gpt-oss:20b")
    )
    native = SimpleNamespace(
        response=AIResponse(
            AIMessage(MessageRole.ASSISTANT, draft),
            BackendInfo("scripted", "offline-control", BackendLocation.LOCAL),
        ),
        tool_results=(),
    )
    calls = []

    def coding(prompt, profile, catalog, **kwargs):
        assert auxiliary_claim not in prompt
        if kwargs.get("progress_prefix") != "scrutiny_activity":
            return prepared
        calls.append(prompt)
        assert draft in prompt and "actual validation passed" in prompt
        if review == "unavailable":
            raise ProviderError("Scripted reviewer unavailable")
        text = (
            "VERDICT: pass\nSCORE: 8"
            if review == "invalid"
            else f"VERDICT: {'needs_revision' if review == 'bold_needs_revision' else review}\n"
            "SCORE: 4\nSTRENGTHS: helper checks pass\n"
            f"ISSUES: {issue}\nRECOMMENDED_NEXT_ACTION: Retract the unsupported claim.\n"
            f"REVISED_RESPONSE: {revision}"
        )
        if review == "bold_needs_revision":
            text = (
                text.replace("STRENGTHS: ", "**STRENGTHS**\n")
                .replace("ISSUES: ", "**ISSUES**\n")
                .replace("REVISED_RESPONSE: ", "**REVISED_RESPONSE**\n")
            )
        return replace(
            prepared,
            response=replace(native.response, message=AIMessage(MessageRole.ASSISTANT, text)),
        )

    monkeypatch.setattr(_EXAMPLE, "run_coding_prompt", coding)
    monkeypatch.setattr(_EXAMPLE, "_run_native_agent", lambda *a, **k: native)
    monkeypatch.setattr(
        _EXAMPLE,
        "run_auxiliary_panel",
        lambda *a, **k: _EXAMPLE.AuxiliaryPanelResult(
            status="completed", response_text=auxiliary_claim
        ),
    )
    monkeypatch.setattr(
        _EXAMPLE,
        "create_chat_client",
        lambda *a, **k: pytest.fail("Offline control attempted real model creation"),
    )
    database = tmp_path / "run.sqlite3"
    if mode == "coding-chat":
        # Automated fixture continuation, never physical owner input.
        monkeypatch.setattr("sys.stdin", StringIO("/exit\n"))
        monkeypatch.setattr("builtins.input", lambda *a: "/exit")
    assert (
        main(
            [
                "--mode",
                mode,
                "Scripted offline delivery control.",
                "--provider",
                "ollama",
                "--model",
                "gpt-oss:20b",
                "--execute",
                "--skip-prompt-review",
                "--orchestrated",
                "--away-minutes",
                "1",
                "--repo-root",
                str(tmp_path),
                "--user-config",
                str(tmp_path / "user-config.toml"),
                "--away-run-db",
                str(database),
                "--coding-session-db",
                str(tmp_path / "coding.sqlite3"),
                "--max-repair-cycles",
                "0",
                "--scrutiny-policy",
                scrutiny_policy,
                "--validation-command",
                f'"{_EXAMPLE.sys.executable}" -B validate.py',
                "--validation-timeout-seconds",
                "10",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert output.index(AUXILIARY_RESPONSE_NOTICE) < output.index(auxiliary_claim)
    final = output.rsplit("## **SUMMARY**", 1)[1]
    assert len(calls) == 1
    assert (tmp_path / "validate.py").read_text(encoding="utf-8") == validator
    assert process_identity(int((tmp_path / "validation.pid").read_text())) is None
    assert "- Validated: passed" in final
    run_id = next(
        line.split(": ", 1)[1] for line in output.splitlines() if line.startswith("away_run_id: ")
    )
    stages = {
        stage.name: stage for stage in SQLiteOrchestratedRunStore(database).list_stages(run_id)
    }
    validation_details = stages["validation"].details
    assert validation_details is not None and validation_details["validation_status"] == "passed"
    assert stages["repair"].status == "skipped"
    scrutiny_details = stages["scrutiny"].details
    if review == "pass":
        # Deliberate reviewer miss: do not pretend the CLI discovered this seeded false claim.
        assert f"### Agent report\n{draft}" in final
        assert "unresolved scrutiny" not in final
        assert "completion=not_established" not in final
    elif review == "invalid":
        # Only the verdict is readable here; every supporting section is missing.
        # ADR-066 treats a readable verdict as the judgement and records the
        # format gap instead of gating on report shape, under either policy.
        assert scrutiny_details is not None
        assert scrutiny_details["verdict"] == "pass"
        assert scrutiny_details["format_issues"]
        assert "completion=not_established" not in final
        assert f"### Agent report\n{draft}" in final
        assert "Agent-reported outcome:" in final
        assert "Reviewer-proposed revision" not in final
    elif review == "unavailable":
        # Missing review evidence is not an advisory judgement: it blocks either way.
        assert "completion=not_established" in final
        assert f"### Agent report — draft with unresolved scrutiny\n{draft}" in final
        assert final.count(draft) == 1
        assert "Agent-reported outcome:" not in final
        assert "Review failure" in final
        assert "Reviewer-proposed revision" not in final
    else:
        assert issue in final and revision in final
        assert "Reviewer-proposed revision (not applied or independently verified)" in final
        assert scrutiny_details is not None and scrutiny_details["revised_response"] == revision
        if scrutiny_policy == "required":
            # ADR-066 keeps the blocking behaviour available on request.
            assert "completion=not_established" in final
            assert f"### Agent report — draft with unresolved scrutiny\n{draft}" in final
            assert final.count(draft) == 1
            assert "Agent-reported outcome:" not in final
        else:
            # ADR-066 default: findings are shown and do not gate the outcome.
            assert "completion=not_established" not in final
            assert "### Scrutiny findings (advisory)" in final
            assert f"### Agent report\n{draft}" in final
            assert "Agent-reported outcome:" in final

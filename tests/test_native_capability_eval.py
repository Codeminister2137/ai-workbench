"""Native evaluation admission and receipts without model inference."""

import copy
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest
from ai_provider import native_capability_eval as native
from ai_provider.external_agents import (
    ExternalAgentEventSummary,
    ExternalAgentResult,
    build_external_agent_command,
)


def reading(used=5):
    return {
        "status": "available",
        "cleanup_verified": True,
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "windows": [
            {
                "bucket_id": "codex",
                "window": name,
                "used_percent": used,
                "resets_at_unix_seconds": 2100000000,
            }
            for name in ("primary", "secondary")
        ],
    }


@pytest.mark.parametrize(
    "change",
    [
        {"status": "unknown"},
        {"cleanup_verified": False},
        {"observed_at_utc": (datetime.now(UTC) - timedelta(seconds=90)).isoformat()},
        {"observed_at_utc": datetime.now().isoformat()},
        {"windows": []},
    ],
)
def test_invalid_snapshots_refuse(change):
    with pytest.raises(ValueError):
        native.checked_windows(reading() | change)


@pytest.mark.parametrize(
    "field,value",
    [
        ("used_percent", None),
        ("used_percent", True),
        ("used_percent", float("nan")),
        ("used_percent", 100),
        ("resets_at_unix_seconds", None),
        ("resets_at_unix_seconds", 1),
    ],
)
def test_bad_window_refuses(field, value):
    report = reading()
    report["windows"][0][field] = value
    with pytest.raises(ValueError):
        native.checked_windows(report)


def test_missing_and_duplicate_windows_refuse():
    report = reading()
    report["windows"].pop()
    with pytest.raises(ValueError):
        native.checked_windows(report)
    report = reading()
    report["windows"].append(copy.copy(report["windows"][0]))
    with pytest.raises(ValueError):
        native.checked_windows(report)


@pytest.mark.parametrize(
    "used,expected", [(14, "pass"), (15, "unknown"), (19, "unknown"), (4, "unknown")]
)
def test_observed_stop_allows_headroom_without_forecasting(monkeypatch, tmp_path, used, expected):
    setup_probe(monkeypatch, lambda *_: result())
    reports = iter([reading(5), reading(used)])
    monkeypatch.setattr(native, "read_codex_allowance", lambda: next(reports))
    assert native.probe_codex("r", "m", tmp_path / "eval.json").status == expected
    receipt = json.loads((tmp_path / "eval.json.native/receipt.json").read_text())
    assert receipt["usage"] == {"output_tokens": 8}
    if used >= 15:
        assert receipt["error_type"] == "EvalThresholdStop"


@pytest.mark.parametrize("change", ["reset", "bucket", "secondary"])
def test_shared_guard_rejects_changed_cycles_and_checks_every_window(monkeypatch, tmp_path, change):
    setup_probe(monkeypatch, lambda *_: result())
    after = reading()
    if change == "reset":
        after["windows"][0]["resets_at_unix_seconds"] += 1
    elif change == "bucket":
        for row in after["windows"]:
            row["bucket_id"] = "other"
    else:
        after["windows"][1]["used_percent"] = 15
    reports = iter([reading(), after])
    monkeypatch.setattr(native, "read_codex_allowance", lambda: next(reports))
    assert native.probe_codex("r", "m", tmp_path / "eval.json").status == "unknown"


def setup_probe(monkeypatch, run):
    monkeypatch.setattr("ai_provider.external_agents.default_codex_command", lambda: "codex")
    reads = []

    def read():
        reads.append(True)
        return reading()

    monkeypatch.setattr(native, "read_codex_allowance", read)
    monkeypatch.setattr(native, "run_external_agent", run)
    return reads


def result(answer='{"answer":7}', tools=()):
    return ExternalAgentResult(
        command=("codex",),
        returncode=0,
        stdout="",
        stderr="",
        last_message=answer,
        events=ExternalAgentEventSummary(
            final_answer=answer,
            command_events=(),
            tool_events=tools,
            web_search_events=(),
            file_change_events=(),
            usage={"output_tokens": 8},
            failure_reason=None,
            parse_errors=(),
        ),
    )


@pytest.mark.parametrize(
    "answer,expected",
    [(' {"answer":7}', "pass"), ('{"answer":7.0}', "fail"), ('{"answer":7,"extra":1}', "fail")],
)
def test_probe_one_call_and_retained_usage(monkeypatch, tmp_path, answer, expected):
    calls = []

    def run(prompt, config):
        calls.append(config)
        assert config.sandbox == "read-only"
        assert config.timeout_seconds == 180
        assert config.approval_policy == "never"
        command = build_external_agent_command(config)
        assert 'forced_login_method="chatgpt"' in command
        assert 'model_provider="openai"' in command
        assert not config.cwd.is_relative_to(tmp_path)
        assert json.loads(config.output_schema_path.read_text()) == native.SCHEMA
        return result(answer)

    reads = setup_probe(monkeypatch, run)
    output = tmp_path / "eval.json"
    assert native.probe_codex("route", "model", output).status == expected
    assert len(reads) == 2 and len(calls) == 1
    receipt = json.loads((tmp_path / "eval.json.native/receipt.json").read_text())
    assert receipt["usage"] == {"output_tokens": 8}
    with pytest.raises(FileExistsError):
        native.probe_codex("route", "model", output)
    assert len(calls) == 1


def test_timeout_postflight_no_retry(monkeypatch, tmp_path):
    def run(*args):
        raise subprocess.TimeoutExpired("codex", 180)

    reads = setup_probe(monkeypatch, run)
    assert native.probe_codex("r", "m", tmp_path / "eval.json").status == "unknown"
    assert len(reads) == 2
    receipt = json.loads((tmp_path / "eval.json.native/receipt.json").read_text())
    assert receipt["after"]["status"] == "available"


def test_preflight_prevents_inference(monkeypatch, tmp_path):
    setup_probe(monkeypatch, lambda *_: pytest.fail("inference must not start"))
    monkeypatch.setattr(native, "read_codex_allowance", lambda: {"status": "unknown"})
    assert native.probe_codex("r", "m", tmp_path / "eval.json").status == "unknown"


def test_tool_activity_is_not_a_pass(monkeypatch, tmp_path):
    setup_probe(monkeypatch, lambda *_: result(tools=({"name": "unexpected"},)))
    assert native.probe_codex("r", "m", tmp_path / "eval.json").status == "unknown"


def test_postflight_failure_preserves_usage(monkeypatch, tmp_path):
    setup_probe(monkeypatch, lambda *_: result())
    reports = iter([reading(), {"status": "unknown"}])
    monkeypatch.setattr(native, "read_codex_allowance", lambda: next(reports))
    assert native.probe_codex("r", "m", tmp_path / "eval.json").status == "unknown"
    receipt = json.loads((tmp_path / "eval.json.native/receipt.json").read_text())
    assert receipt["usage"] == {"output_tokens": 8}
    assert receipt["after"]["status"] == "unknown"


@pytest.mark.parametrize(
    "hosted,billing", [(False, "chatgpt_subscription_allowance"), (True, "provider_credits")]
)
def test_worker_cli_rejects_unapproved_or_metered_native(monkeypatch, tmp_path, hosted, billing):
    from ai_provider.capability_eval import main

    catalog = tmp_path / "catalog.toml"
    catalog.write_text(
        '[[models]]\nroute_id="native"\nprovider="openai"\nmodel="exact-model"\n'
        f'access_method="codex_cli"\nbilling_source="{billing}"\n'
    )
    args = [
        "capability_eval",
        "--catalog",
        str(catalog),
        "--route",
        "native",
        "--output",
        str(tmp_path / "eval.json"),
    ]
    if hosted:
        args.append("--allow-hosted")
    monkeypatch.setattr(sys, "argv", args)
    monkeypatch.setattr(native, "probe_codex", lambda *_: pytest.fail("must not invoke"))
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert not (tmp_path / "eval.json").exists()


def test_worker_cli_dispatches_exact_native_route(monkeypatch, tmp_path):
    from ai_provider.capability_eval import Verdict, main

    catalog = tmp_path / "catalog.toml"
    catalog.write_text(
        '[[models]]\nroute_id="native"\nprovider="openai"\nmodel="exact-model"\n'
        'access_method="codex_cli"\nbilling_source="chatgpt_subscription_allowance"\n'
    )
    output = tmp_path / "eval.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capability_eval",
            "--catalog",
            str(catalog),
            "--route",
            "native",
            "--output",
            str(output),
            "--allow-hosted",
        ],
    )
    calls = []

    def probe(route, model, path):
        calls.append((route, model, path))
        return Verdict(route, "structured_output", "pass", "now", 1, "fixture")

    monkeypatch.setattr(native, "probe_codex", probe)
    main()
    assert calls == [("native", "exact-model", output)]
    assert json.loads(output.read_text())["status"] == "pass"

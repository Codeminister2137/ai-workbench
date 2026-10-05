"""Saved usage is distinguishable from estimates, unknown quotas and private text."""

import json

import pytest
from ai_provider import acceptance_usage


class TestLocalUsage:
    def test_call_sums_keep_provenance_and_missing_measurements_visible(self, tmp_path):
        result = {
            "usage": [
                {
                    "source": "provider_reported",
                    "input_tokens": 10,
                    "output_tokens": 2,
                    "total_tokens": 12,
                },
                {"source": "provider_reported", "input_tokens": 0, "output_tokens": None},
                {"source": "estimated", "input_tokens": 4, "output_tokens": 1, "total_tokens": 5},
                {"source": "unavailable"},
            ],
            "private_prompt": "must not be exported",
        }
        (tmp_path / "worker-result.json").write_text(json.dumps(result))
        report = acceptance_usage.summarize_usage(tmp_path, "local_free")
        metrics = report["metrics"]
        assert metrics["provider_reported.input_tokens"] == {
            "value": 10,
            "measured_calls": 2,
            "scope": "sum_of_recorded_calls",
        }
        assert metrics["provider_reported.output_tokens"]["measured_calls"] == 1
        assert metrics["estimated.input_tokens"]["value"] == 4
        assert report["observed_calls"] == 4
        assert report["remaining_allowance"] == report["supervisor_usage"] == "unknown"
        assert "private_prompt" not in json.dumps(report)
        assert "must not be exported" not in json.dumps(report)

    def test_missing_receipt_is_unknown_without_creating_state(self, tmp_path):
        report = acceptance_usage.summarize_usage(tmp_path, "local_free")
        assert report["metrics"] == {} and report["evidence"] == []
        assert not list(tmp_path.iterdir())


class TestClientUsage:
    def test_copilot_final_result_supersedes_checkpoint_without_exporting_private_fields(
        self, tmp_path
    ):
        events = [
            {"type": "session.usage_checkpoint", "data": {"totalPremiumRequests": 1}},
            {
                "type": "result",
                "usage": {"premiumRequests": 2, "codeChanges": {"private": "private change"}},
            },
        ]
        (tmp_path / "stdout.jsonl").write_text("\n".join(json.dumps(row) for row in events))
        report = acceptance_usage.summarize_usage(tmp_path, "github_copilot_subscription_allowance")
        assert report["metrics"]["premium_requests"]["value"] == 2
        assert "private" not in json.dumps(report)

    def test_codex_cached_and_reasoning_counts_are_not_added_to_totals(self, tmp_path):
        events = [
            {"type": "turn.completed", "usage": {"input_tokens": 20, "output_tokens": 4}},
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 100,
                    "cached_input_tokens": 80,
                    "output_tokens": 5,
                    "reasoning_output_tokens": 3,
                    "private": "must not be exported",
                },
            },
        ]
        (tmp_path / "stdout.jsonl").write_text("\n".join(json.dumps(row) for row in events))
        report = acceptance_usage.summarize_usage(tmp_path, "chatgpt_subscription_allowance")
        assert report["metrics"]["input_tokens"]["value"] == 100
        assert report["metrics"]["cached_input_tokens"]["value"] == 80
        assert "total_tokens" not in report["metrics"]
        assert "private" not in json.dumps(report)
        assert "must not be exported" not in json.dumps(report)

    def test_copilot_uses_reported_checkpoint_not_inferred_tokens_or_cost(self, tmp_path, capsys):
        event = {
            "type": "session.usage_checkpoint",
            "data": {
                "totalPremiumRequests": 1,
                "totalNanoAiu": 200,
                "modelCacheState": {"secret": "must not be exported"},
            },
        }
        (tmp_path / "stdout.jsonl").write_text(json.dumps(event))
        code = acceptance_usage.main(
            [
                "--run",
                "github_copilot_subscription_allowance",
                str(tmp_path),
            ]
        )
        assert code == 0
        output = capsys.readouterr().out
        assert "premium_requests: 1" in output
        assert "Remaining allowance: unknown" in output
        assert "must not be exported" not in output and "secret" not in output

    def test_kiro_only_exports_recognized_numeric_units(self, tmp_path):
        event = {
            "type": "usage",
            "data": {
                "meteringUsage": [
                    {"unit": "credit", "value": 0.125},
                    {"unit": "private account name", "value": 50},
                    {"unit": {"private": "account"}, "value": 50},
                    {"unit": ["credits"], "value": 50},
                    {"unit": "tokens", "value": True},
                ]
            },
        }
        (tmp_path / "stdout.jsonl").write_text(json.dumps(event))
        report = acceptance_usage.summarize_usage(tmp_path, "kiro_subscription_allowance")
        assert report["metrics"] == {
            "meter.credit": {"value": 0.125, "scope": "reported_meter_entry"}
        }
        assert "private account name" not in json.dumps(report)

    def test_repeated_meter_units_do_not_get_overwritten_or_guessed_as_additive(self, tmp_path):
        event = {
            "type": "usage",
            "data": {
                "meteringUsage": [
                    {"unit": "credit", "value": 0.1},
                    {"unit": "credit", "value": 0.2},
                ]
            },
        }
        (tmp_path / "stdout.jsonl").write_text(json.dumps(event))
        report = acceptance_usage.summarize_usage(tmp_path, "kiro_subscription_allowance")
        assert report["metrics"] == {
            "meter.credit[0]": {"value": 0.1, "scope": "reported_meter_entry"},
            "meter.credit[1]": {"value": 0.2, "scope": "reported_meter_entry"},
        }
        assert any("Repeated meter" in note for note in report["notes"])


class TestReceiptAdmission:
    def test_partial_jsonl_measurements_warn_and_return_failure_without_raw_lines(
        self, tmp_path, capsys
    ):
        (tmp_path / "stdout.jsonl").write_text(
            'private-secret-invalid-json\n{"type":"turn.completed","usage":{"input_tokens":10}}'
        )
        assert (
            acceptance_usage.main(["--run", "chatgpt_subscription_allowance", str(tmp_path)]) == 1
        )
        output = capsys.readouterr().out
        assert "input_tokens: 10" in output and "1 malformed lines" in output
        assert "private-secret" not in output

    @pytest.mark.parametrize("value", [True, -1, float("inf"), float("nan"), "123"])
    def test_invalid_token_values_are_not_measurements(self, tmp_path, value):
        event = {"type": "turn.completed", "usage": {"input_tokens": value}}
        (tmp_path / "stdout.jsonl").write_text(json.dumps(event))
        assert (
            acceptance_usage.summarize_usage(tmp_path, "chatgpt_subscription_allowance")["metrics"]
            == {}
        )

    def test_malformed_receipt_reports_failure_without_printing_contents(self, tmp_path, capsys):
        (tmp_path / "worker-result.json").write_text("private-secret-not-json")
        assert acceptance_usage.main(["--run", "local_free", str(tmp_path)]) == 1
        assert "private-secret" not in capsys.readouterr().out

    def test_explicit_source_and_bounded_files_are_required(self, tmp_path, monkeypatch):
        with pytest.raises(ValueError, match="explicit billing"):
            acceptance_usage.summarize_usage(tmp_path, "guessed")
        target = tmp_path / "stdout.jsonl"
        target.write_bytes(b"x" * 20)
        monkeypatch.setattr(acceptance_usage, "READ_LIMIT", 10)
        with pytest.raises(ValueError, match="read limit"):
            acceptance_usage.summarize_usage(tmp_path, "chatgpt_subscription_allowance")

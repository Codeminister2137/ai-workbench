"""CLI `run` output prints the effective fan-out policy once at run start."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "publish-loop-plans.py"
spec = importlib.util.spec_from_file_location("publish_loop_plans", SCRIPT)
assert spec is not None
assert spec.loader is not None
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def _run_args(tmp_path, *extra: str) -> list[str]:
    return ["--data-dir", str(tmp_path / "data"), "run", *extra]


def test_run_prints_unknown_fanout_once(tmp_path, capsys) -> None:
    code = cli.main(_run_args(tmp_path, "--id", "r1", "--title", "R", "--status", "running"))
    assert code == 0
    out = capsys.readouterr().out
    assert "wrote r1" in out
    assert out.count("fanout: unknown") == 1


def test_run_prints_stored_effective_policy(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "sync_run",
        lambda stores, **kwargs: {"id": "r1", "fanout_effective": "restricted"},
    )
    code = cli.main(_run_args(tmp_path, "--id", "r1", "--title", "R", "--status", "running"))
    assert code == 0
    out = capsys.readouterr().out
    assert out.count("fanout: restricted") == 1


def test_plan_output_has_no_fanout_line(tmp_path, capsys) -> None:
    plan_file = tmp_path / "loop.md"
    plan_file.write_text("# Loop\n", encoding="utf-8")
    code = cli.main(
        [
            "--data-dir",
            str(tmp_path / "data"),
            "plan",
            "--id",
            "loop-1",
            "--title",
            "L",
            "--file",
            str(plan_file),
            "--status",
            "open",
        ]
    )
    assert code == 0
    assert "fanout:" not in capsys.readouterr().out

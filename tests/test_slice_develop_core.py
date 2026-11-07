"""Shared slice-driver core: accept/reject/retry/receipt with a fake client."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/slice_develop_core.py"
SPEC = importlib.util.spec_from_file_location("slice_develop_core", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


class FakeClient:
    """Scripted model: each complete() pops the next content or raises it."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def complete(self, request):
        self.calls += 1
        assert request.model
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(
            message=SimpleNamespace(content=item),
            finish_reason=SimpleNamespace(value="stop"),
            usage=None,
        )


def _ok_run(*args, **kwargs):
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def test_accept_path_writes_and_receipts(tmp_path, monkeypatch) -> None:
    (tmp_path / "mod.py").write_text("X = 0\n", encoding="utf-8")
    monkeypatch.setattr(core.subprocess, "run", _ok_run)
    client = FakeClient([json.dumps({"changes": {"mod.py": "X = 1\n"}})])
    receipt = core.drive_slice(
        root=tmp_path,
        client=client,
        model="fake-model",
        slice_name="s1",
        brief="Set X to 1.",
        allow={"mod.py"},
        pytest_files=["tests/test_x.py"],
        phase=tmp_path / "phase",
        max_calls=2,
        cap=1024,
        purpose="test-slice",
    )
    assert receipt["status"] == "accepted"
    assert len(receipt["sends"]) == 1
    assert (tmp_path / "mod.py").read_text(encoding="utf-8") == "X = 1\n"
    saved = json.loads((tmp_path / "phase" / "receipt.json").read_text(encoding="utf-8"))
    assert saved["status"] == "accepted"


def test_reject_restores_pristine_then_accepts(tmp_path, monkeypatch) -> None:
    (tmp_path / "mod.py").write_text("X = 0\n", encoding="utf-8")
    monkeypatch.setattr(core.subprocess, "run", _ok_run)
    client = FakeClient(
        [
            "no json here",
            json.dumps({"changes": {"mod.py": "X = 2\n"}}),
        ]
    )
    receipt = core.drive_slice(
        root=tmp_path,
        client=client,
        model="fake-model",
        slice_name="s2",
        brief="Set X to 2.",
        allow={"mod.py"},
        pytest_files=[],
        phase=tmp_path / "phase",
        max_calls=2,
        cap=1024,
        purpose="test-slice",
    )
    assert receipt["status"] == "accepted"
    assert [send["status"] for send in receipt["sends"]] == [
        "rejected: Model response contained no JSON object",
        "received",
    ]
    assert (tmp_path / "mod.py").read_text(encoding="utf-8") == "X = 2\n"


def test_test_growth_rule_rejects_shrinking_tests(tmp_path, monkeypatch) -> None:
    test_file = tmp_path / "tests" / "test_x.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_one():\n    assert True\n", encoding="utf-8")
    monkeypatch.setattr(core.subprocess, "run", _ok_run)
    client = FakeClient([json.dumps({"changes": {"tests/test_x.py": "CONST = 1\n"}})])
    receipt = core.drive_slice(
        root=tmp_path,
        client=client,
        model="fake-model",
        slice_name="s3",
        brief="Shrink tests.",
        allow={"tests/test_x.py"},
        pytest_files=[],
        phase=tmp_path / "phase",
        max_calls=1,
        cap=1024,
        purpose="test-slice",
    )
    assert receipt["status"] == "attempts_exhausted"
    assert "gained no test functions" in receipt["sends"][0]["status"]
    assert "def test_one" in test_file.read_text(encoding="utf-8")


def test_prompt_over_bound_fails_without_calling(tmp_path) -> None:
    (tmp_path / "big.py").write_text("X = 1\n" * 20000, encoding="utf-8")
    client = FakeClient([])
    receipt = core.drive_slice(
        root=tmp_path,
        client=client,
        model="fake-model",
        slice_name="s4",
        brief="Too big.",
        allow={"big.py"},
        pytest_files=[],
        phase=tmp_path / "phase",
        max_calls=2,
        cap=1024,
        purpose="test-slice",
    )
    assert receipt["status"] == "failed"
    assert receipt["sends"][0]["status"] == "prompt_over_bound"
    assert client.calls == 0


def test_transport_failure_recorded(tmp_path) -> None:
    (tmp_path / "mod.py").write_text("X = 0\n", encoding="utf-8")
    client = FakeClient([RuntimeError("boom")])
    receipt = core.drive_slice(
        root=tmp_path,
        client=client,
        model="fake-model",
        slice_name="s5",
        brief="Unreachable.",
        allow={"mod.py"},
        pytest_files=[],
        phase=tmp_path / "phase",
        max_calls=3,
        cap=1024,
        purpose="test-slice",
    )
    assert receipt["status"] == "failed"
    assert receipt["sends"][0]["status"] == "transport_failed"


def test_read_env_key_requires_exactly_one(tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text("OTHER_KEY=x\n", encoding="utf-8")
    try:
        core.read_env_key(tmp_path, "WANT_KEY", label="wanted")
    except ValueError as exc:
        assert "Exactly one wanted is required" in str(exc)
    else:
        raise AssertionError("missing key accepted")
    env.write_text("WANT_KEY=a\nWANT_KEY=b\n", encoding="utf-8")
    try:
        core.read_env_key(tmp_path, "WANT_KEY", label="wanted")
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate key accepted")


def test_run_checks_reports_pytest_failure_and_falls_back(tmp_path, monkeypatch) -> None:
    seen = []

    def fake_run(argv, **kwargs):
        seen.append(argv)
        return SimpleNamespace(returncode=3, stdout="F", stderr="")

    monkeypatch.setattr(core.subprocess, "run", fake_run)
    import sys

    ok, output = core.run_checks(tmp_path, ["tests/test_x.py"], ["mod.py"])
    assert ok is False
    assert "pytest exit=3" in output
    assert seen[0][0] == sys.executable

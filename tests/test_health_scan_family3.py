"""Health scan clone subprocess contract and immutable receipts."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/health_scan_family3.py"
SPEC = importlib.util.spec_from_file_location("health_scan", SCRIPT)
assert SPEC and SPEC.loader
wrapper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wrapper)


@pytest.mark.parametrize(
    "mode", ["exit", "parse", "schema", "stderr", "timeout", "oserror", "clean"]
)
def test_clone_failures_cannot_report_clean(tmp_path, monkeypatch, mode):
    def run(*args, **kwargs):
        if mode == "timeout":
            raise subprocess.TimeoutExpired(
                "scanner", 600, output="partial", stderr="timeout detail"
            )
        if mode == "oserror":
            raise OSError("cannot launch")
        return subprocess.CompletedProcess(
            args[0],
            7 if mode == "exit" else 0,
            "human text" if mode == "parse" else "{}" if mode == "schema" else "[]",
            "detail" if mode in ("exit", "stderr") else "",
        )

    monkeypatch.setattr(wrapper.subprocess, "run", run)
    out = tmp_path / "receipt.json"
    result = wrapper.main(["--root", str(tmp_path), "--output", str(out)])
    receipt = json.loads(out.read_text())
    assert result == (0 if mode == "clean" else 1)
    assert (receipt["status"] == "COMPLETE") == (mode == "clean")
    if mode != "clean":
        assert receipt["clone_scan"]["diagnostic"]
    if mode in ("exit", "stderr"):
        assert receipt["clone_scan"]["stderr"] == "detail"
    if mode in ("parse", "schema", "exit", "timeout", "oserror"):
        assert receipt["clone_groups"] is None


def test_existing_receipt_preserved(tmp_path):
    out = tmp_path / "receipt.json"
    out.write_bytes(b"consumed receipt")
    with pytest.raises(SystemExit):
        wrapper.main(["--output", str(out)])
    assert out.read_bytes() == b"consumed receipt"


@pytest.mark.parametrize("absolute", [True, False])
def test_direct_scanner_agrees_with_wrapper(tmp_path, monkeypatch, absolute):
    import sys

    root = tmp_path / ".tmp" / "repo"
    for top in wrapper.INCLUDE_TOPS:
        (root / top).mkdir(parents=True)
    scanner = SCRIPT.with_name("find-duplication.py")
    (root / "scripts" / scanner.name).write_bytes(scanner.read_bytes())
    body = (
        "def clone(values):\n"
        + "".join(f"    value{i} = values + {i}\n" for i in range(16))
        + "    return value0\n"
    )
    for name in ("a", "b"):
        (root / "apps" / f"{name}.py").write_text(body)
    monkeypatch.chdir(root.parent)
    arg = str(root) if absolute else "repo"
    direct = subprocess.run(
        [
            sys.executable,
            str(scanner),
            *[str(Path(arg) / top) for top in wrapper.INCLUDE_TOPS],
            "--min-lines",
            "15",
            "--json",
            "-",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    out = tmp_path / "new.json"
    assert wrapper.main(["--root", arg, "--output", str(out)]) == 0
    actual = json.loads(out.read_text())["clone_groups"]
    assert len(actual) == len(json.loads(direct.stdout)) == 1


def test_real_scanner_warning_prevents_complete_receipt(tmp_path):
    root = tmp_path / "repo"
    for top in wrapper.INCLUDE_TOPS:
        (root / top).mkdir(parents=True)
    scanner = SCRIPT.with_name("find-duplication.py")
    (root / "scripts" / scanner.name).write_bytes(scanner.read_bytes())
    (root / "apps" / "broken.py").write_text("def broken(:\n")
    out = tmp_path / "warning.json"
    assert wrapper.main(["--root", str(root), "--output", str(out)]) == 1
    receipt = json.loads(out.read_text())
    assert receipt["status"] == "UNKNOWN"
    assert receipt["clone_scan"]["returncode"] == 0
    assert "broken.py" in receipt["clone_scan"]["stderr"]
    assert receipt["clone_scan"]["diagnostic"]

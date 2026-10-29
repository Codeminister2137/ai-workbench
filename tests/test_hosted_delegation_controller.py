"""Evidence-integrity controls for the offline-only delegation controller."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/hosted-delegation-acceptance.py"
SPEC = importlib.util.spec_from_file_location("offline_delegation_controller", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
controller = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(controller)


def test_output_cannot_escape_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(controller, "ROOT", tmp_path)
    target = tmp_path / "outside"
    with pytest.raises(SystemExit):
        controller.main(["--output-dir", str(target)])
    assert not target.exists()


def test_consumed_receipt_cannot_be_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(controller, "ROOT", tmp_path)
    target = tmp_path / "artifacts" / "consumed"
    target.mkdir(parents=True)
    receipt = target / "receipt.json"
    receipt.write_text("preserve consumed evidence")
    with pytest.raises(FileExistsError):
        controller.main(["--output-dir", str(target)])
    assert receipt.read_text() == "preserve consumed evidence"


@pytest.mark.parametrize(
    "failure",
    [
        "required_test_skipped",
        "cleanup_unverified",
        "source_changed",
        "duplicate_case",
        "wrong_class",
        "missing_case",
    ],
)
def test_zero_exit_cannot_promote_missing_evidence(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(controller, "ROOT", tmp_path)
    monkeypatch.setattr(controller, "SOURCES", ("source.py",))
    (tmp_path / "source.py").write_text("synthetic source")
    target = tmp_path / "artifacts" / "fresh"

    class Child:
        process = SimpleNamespace(poll=lambda: 0)

        def __init__(self, argv, *, env, **kwargs):
            assert "META_API_KEY" not in env
            assert "BASETEN_HACKATHON_API_KEY" not in env
            names = sorted(controller.REQUIRED_CASES)
            if failure == "duplicate_case":
                names[-1] = names[0]
            if failure == "missing_case":
                names.pop()
            cases = "".join(
                f'<testcase name="{name}" classname="'
                + ("wrong_class" if failure == "wrong_class" else controller.REQUIRED_CLASSES[name])
                + '">'
                + ("<skipped/>" if failure == "required_test_skipped" and index == 0 else "")
                + "</testcase>"
                for index, name in enumerate(names)
            )
            (target / "junit.xml").write_text("<testsuites>" + cases + "</testsuites>")

        def wait(self, deadline):
            if failure == "source_changed":
                (tmp_path / "source.py").write_text("changed during execution")
            return 0

        def stop(self, timeout):
            return failure != "cleanup_unverified"

    monkeypatch.setenv("META_API_KEY", "synthetic-must-not-inherit")
    monkeypatch.setenv("BASETEN_HACKATHON_API_KEY", "synthetic-must-not-inherit-either")
    monkeypatch.setattr(controller, "OwnedChild", Child)
    assert controller.main(["--output-dir", str(target)]) == 1
    receipt = json.loads((target / "receipt.json").read_text())
    assert receipt["status"] == "failed"
    assert receipt["exit_code"] == 0
    assert receipt["stage"] == "finished"
    assert receipt["required_checks_passed"] is (
        failure in {"cleanup_unverified", "source_changed"}
    )


def test_no_live_activation_option(tmp_path, monkeypatch):
    monkeypatch.setattr(controller, "ROOT", tmp_path)
    target = tmp_path / "artifacts" / "never_created"
    with pytest.raises(SystemExit):
        controller.main(["--output-dir", str(target), "--live"])
    assert not target.exists()

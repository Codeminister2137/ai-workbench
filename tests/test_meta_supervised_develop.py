"""Offline checks of trusted launcher admission; no provider or candidate execution."""

import importlib.util
import json
import time
from argparse import Namespace
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/meta-supervised-develop.py"
spec = importlib.util.spec_from_file_location("meta_supervised_develop", SCRIPT)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


@pytest.fixture
def job(tmp_path, monkeypatch):
    root = tmp_path / "private"
    public = tmp_path / "remote-ai-operator"
    phase = root / "artifacts/job"
    phase.mkdir(parents=True)
    (public / "src").mkdir(parents=True)
    (public / "AGENTS.md").write_text("public instructions", encoding="utf-8")
    (public / "src/task.py").write_text("before", encoding="utf-8")
    task = phase / "task.txt"
    task.write_text("Implement an approved public task", encoding="utf-8")
    for name in launcher.VALIDATOR_FILES:
        (phase / name).write_text(
            json.dumps({"attempts": 0, "expires_epoch": time.time() + 3600})
            if name.endswith("json")
            else "protected",
            encoding="utf-8",
        )
    monkeypatch.setattr(launcher, "ROOT", root)
    monkeypatch.setattr(launcher, "PUBLIC_GIT", public / ".git")
    monkeypatch.setattr(launcher.subprocess, "check_output", lambda *a, **k: str(public / ".git"))
    return Namespace(
        repo_root=public, phase=phase, task_file=task, file=["src/task.py"], context=[], max_calls=8
    )


def test_admission_binds_source_policy_and_budget(job):
    original, seal = launcher.prepare(job)
    assert original["targets"]["src/task.py"] == launcher.digest(b"before")
    (job.repo_root / "src/task.py").write_text("changed", encoding="utf-8")
    assert launcher.prepare(job)[1] != seal
    (job.repo_root / "src/task.py").write_text("before", encoding="utf-8")
    (job.phase / "checks.txt").write_text("changed protected checks", encoding="utf-8")
    assert launcher.prepare(job)[1] != seal
    (job.phase / "checks.txt").write_text("protected", encoding="utf-8")
    job.max_calls += 1
    assert launcher.prepare(job)[1] != seal


def test_private_repository_is_refused_before_payload(job, monkeypatch):
    monkeypatch.setattr(
        launcher.subprocess, "check_output", lambda *a, **k: str(job.phase / ".git")
    )
    with pytest.raises(ValueError, match="public Operator"):
        launcher.prepare(job)


@pytest.mark.parametrize(
    "name",
    [
        "../secrets.py",
        "src/../secret.py",
        ".env",
        "src/.env.py",
        "src\\task.py",
        "C:/x.py",
        "/src/task.py",
        "src/task.py:secret",
        "src/task.py\n",
        "docs//private.md",
    ],
)
def test_secret_ambiguous_and_escaping_paths_refused(job, name):
    with pytest.raises(ValueError):
        launcher.safe_file(job.repo_root, name)


def test_consumed_validator_cannot_start_another_phase(job):
    (job.phase / "modal-allowance.json").write_text('{"attempts":1}', encoding="utf-8")
    with pytest.raises(ValueError, match="Consumed"):
        launcher.prepare(job)


def test_unadmitted_job_does_not_create_receipt(job):
    prepared, seal = launcher.prepare(job)
    (job.phase / "AUTHORIZED").write_text("wrong scope", encoding="utf-8")
    with pytest.raises(ValueError, match="not been admitted"):
        launcher.execute(job, prepared, seal, None)
    assert not (job.phase / "receipt.json").exists()


def test_expired_allowance_stops_before_any_provider_request(job):
    (job.phase / "modal-allowance.json").write_text(
        '{"attempts":0,"expires_epoch":0}', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="expired"):
        launcher.prepare(job)


def test_existing_receipt_is_preserved_before_import_or_credentials(job):
    prepared, seal = launcher.prepare(job)
    (job.phase / "AUTHORIZED").write_text(seal, encoding="utf-8")
    (job.phase / "receipt.json").write_text("original evidence", encoding="utf-8")
    with pytest.raises(FileExistsError):
        launcher.execute(job, prepared, seal, None)
    assert (job.phase / "receipt.json").read_text() == "original evidence"


def test_reviewed_host_tree_changes_and_extra_code_are_refused(tmp_path, monkeypatch):
    source = tmp_path / "trusted"
    source.mkdir()
    module = source / "control.py"
    module.write_bytes(b"reviewed")
    manifest = {"control.py": launcher.digest(b"reviewed")}
    seal = launcher.digest(json.dumps(manifest, sort_keys=True).encode())
    monkeypatch.setattr(launcher, "TRUSTED_SOURCE", source)
    monkeypatch.setattr(launcher, "TRUSTED_SHA256", seal)
    launcher.verify_trusted_source()
    module.write_bytes(b"candidate")
    with pytest.raises(ValueError, match="host control source changed"):
        launcher.verify_trusted_source()
    module.write_bytes(b"reviewed")
    (source / "unexpected.py").write_bytes(b"unreviewed")
    with pytest.raises(ValueError, match="host control source changed"):
        launcher.verify_trusted_source()

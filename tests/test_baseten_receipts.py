"""Offline checks for validator receipt freshness across retries."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/baseten-supervised-develop.py"
spec = importlib.util.spec_from_file_location("baseten_supervised_develop", SCRIPT)
assert spec is not None
assert spec.loader is not None
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


def test_fresh_reports_detects_new_receipt(tmp_path):
    before = worker.snapshot_receipts(tmp_path)
    assert before == {}
    (tmp_path / "modal-1.json").write_text("{}", encoding="utf-8")
    assert worker.fresh_reports(before, tmp_path) == {tmp_path / "modal-1.json"}


def test_fresh_reports_accepts_overwritten_retry_receipt(tmp_path):
    target = tmp_path / "modal-1.json"
    target.write_text('{"exit_code": 2}', encoding="utf-8")
    before = worker.snapshot_receipts(tmp_path)
    target.write_text('{"exit_code": 0}', encoding="utf-8")
    assert worker.fresh_reports(before, tmp_path) == {target}


def test_fresh_reports_empty_when_nothing_changed(tmp_path):
    target = tmp_path / "modal-1.json"
    target.write_text('{"exit_code": 0}', encoding="utf-8")
    before = worker.snapshot_receipts(tmp_path)
    assert worker.fresh_reports(before, tmp_path) == set()

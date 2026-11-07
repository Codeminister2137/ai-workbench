"""Scheduled clone-scan: new-group detection and baseline handling."""

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/clone-scan-scheduled.py"
SPEC = importlib.util.spec_from_file_location("clone_scan_scheduled", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def _group(key, nodes, *members):
    head = {"key": key, "nodes": nodes, "path": "a.py", "lineno": 1, "name": "f"}
    group = [dict(head)]
    for path, lineno, name in members:
        group.append({"key": key, "nodes": nodes, "path": path, "lineno": lineno, "name": name})
    return group


def test_group_keys_are_stable_and_sorted():
    groups = [_group("k1", 40, ("b.py", 9, "g"), ("a.py", 3, "f"))]
    keyed = mod.group_keys(groups)
    assert keyed == {"k1:40": ["a.py:1: f", "a.py:3: f", "b.py:9: g"]}


def test_find_new_reports_only_unseen_keys():
    current = {"k1:40": ["a"], "k2:50": ["b"]}
    baseline = {"groups": {"k1:40": {"members": ["a"], "first_seen_utc": "t"}}}
    assert mod.find_new(current, baseline) == {"k2:50": ["b"]}
    assert mod.find_new(current, {"groups": dict(current)}) == {}


def test_disappeared_groups_do_not_brief():
    current = {"k1:40": ["a"]}
    baseline = {"groups": {"k1:40": {}, "k9:99": {}}}
    assert mod.find_new(current, baseline) == {}


def test_brief_body_contains_member_names():
    body = mod.build_brief_body({"k2:50": ["b.py:9: g"]}, total=25)
    assert "1 new group(s) (25 total)" in body
    assert "key=k2:50" in body
    assert "b.py:9: g" in body


def test_first_run_establishes_baseline(tmp_path, monkeypatch):
    baseline = tmp_path / "baseline.json"
    monkeypatch.setattr(mod.scanner, "iter_python_files", lambda roots: [])
    code = mod.main(
        ["--repo-root", str(tmp_path), "--baseline", str(baseline), "--dashboard", "http://nope"]
    )
    assert code == 0
    stored = json.loads(baseline.read_text(encoding="utf-8"))
    assert stored["groups"] == {}
    assert stored["updated_utc"]


def test_no_new_groups_writes_nothing(tmp_path, monkeypatch):
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"groups": {}, "updated_utc": "t"}), encoding="utf-8")
    before = baseline.read_text(encoding="utf-8")
    monkeypatch.setattr(mod.scanner, "iter_python_files", lambda roots: [])
    code = mod.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
    assert code == 0
    assert baseline.read_text(encoding="utf-8") == before


def test_new_groups_file_brief_and_update_baseline(tmp_path, monkeypatch):
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"groups": {}, "updated_utc": "t"}), encoding="utf-8")
    posted = {}

    def fake_file(dashboard, title, body):
        posted["dashboard"] = dashboard
        posted["title"] = title
        posted["body"] = body

    monkeypatch.setattr(mod, "file_brief", fake_file)
    monkeypatch.setattr(
        mod.scanner,
        "find_groups",
        lambda records, **kwargs: [
            [
                {"key": "k2", "nodes": 50, "path": "b.py", "lineno": 9, "name": "g"},
                {"key": "k2", "nodes": 50, "path": "c.py", "lineno": 2, "name": "h"},
            ]
        ],
    )
    monkeypatch.setattr(mod.scanner, "iter_python_files", lambda roots: [tmp_path])
    code = mod.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
    assert code == 0
    assert posted["title"] == "Clone scan: 1 new group(s)"
    assert "b.py:9: g" in posted["body"]
    stored = json.loads(baseline.read_text(encoding="utf-8"))
    assert "k2:50" in stored["groups"]
    assert stored["groups"]["k2:50"]["first_seen_utc"]
    assert (tmp_path / "runs.log").exists()

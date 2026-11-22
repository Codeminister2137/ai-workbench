"""Focused tests for the forgotten-items sweep collectors."""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent / "scripts" / "forgotten_sweep.py"


def _load():
    spec = importlib.util.spec_from_file_location("forgotten_sweep", HERE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SWEEP = _load()
NOW = datetime.now(UTC)


def _ts(hours_ago: float) -> str:
    return (NOW - timedelta(hours=hours_ago)).isoformat()


def _repo_with(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def test_p4_flags_stale_credential_blockers(tmp_path: Path) -> None:
    repo = _repo_with(
        tmp_path,
        {
            ".env": "PROSPEO_API_KEY=x\nOTHER=1\n",
            "docs/decisions.md": "Trial blocked on account creation for Prospeo.\n",
        },
    )
    findings = SWEEP.collect_stale_blockers(repo)
    assert len(findings) == 1
    assert findings[0]["category"] == "P4"
    assert "PROSPEO_API_KEY" in findings[0]["title"]


def test_p4_silent_on_corrected_records(tmp_path: Path) -> None:
    repo = _repo_with(
        tmp_path,
        {
            ".env": "PROSPEO_API_KEY=x\n",
            "docs/decisions.md": (
                "## Vendor trial: Prospeo\n\n"
                "Trial blocked on account creation.\n\n"
                "Update 2026-11-17: accounts created, key configured.\n"
            ),
        },
    )
    assert SWEEP.collect_stale_blockers(repo) == []


def test_p4_silent_without_keys_or_claims(tmp_path: Path) -> None:
    repo = _repo_with(
        tmp_path,
        {
            ".env": "OTHER=1\n",
            "docs/decisions.md": "Trial blocked on account creation for Prospeo.\n",
        },
    )
    assert SWEEP.collect_stale_blockers(repo) == []
    repo2 = _repo_with(
        tmp_path / "b",
        {".env": "PROSPEO_API_KEY=x\n", "docs/decisions.md": "All good.\n"},
    )
    assert SWEEP.collect_stale_blockers(repo2) == []


def test_r6_flags_terminal_runs_never_reported_back() -> None:
    runs = [
        {
            "id": "orphan1",
            "title": "Done silently",
            "status": "completed",
            "created_at_utc": _ts(100),
            "finished_at_utc": _ts(90),
            "bridged_from": "in1",
        },
        {
            "id": "noted1",
            "title": "Done loudly",
            "status": "completed",
            "created_at_utc": _ts(100),
            "finished_at_utc": _ts(90),
            "bridged_from": "in2",
        },
    ]
    inbox = [
        {"id": "in1", "title": "t", "status": "open", "note": ""},
        {"id": "in2", "title": "t", "status": "open", "note": "Run noted1 completed"},
    ]
    findings, _resolved = SWEEP.collect_runs(runs, inbox, NOW, ())
    r6 = [f for f in findings if f["category"] == "R6"]
    assert len(r6) == 1
    assert r6[0]["members"][0]["id"] == "orphan1"


def test_r1_flags_failed_without_followup_and_skips_superseded() -> None:
    runs = [
        {
            "id": "aaa",
            "title": "Old fail",
            "status": "failed",
            "created_at_utc": _ts(100),
            "inbox_id": "i1",
            "error": "boom",
        },
        {
            "id": "bbb",
            "title": "Old fail then retried",
            "status": "failed",
            "created_at_utc": _ts(100),
            "inbox_id": "i2",
        },
        {
            "id": "ccc",
            "title": "Retry ok",
            "status": "completed",
            "created_at_utc": _ts(90),
            "inbox_id": "i2",
        },
        {
            "id": "ddd",
            "title": "Fresh fail",
            "status": "failed",
            "created_at_utc": _ts(1),
            "inbox_id": None,
        },
    ]
    findings, _resolved = SWEEP.collect_runs(runs, [], NOW)
    by_key = {f["key"]: f for f in findings}
    assert by_key["R1:aaa"]["fileable"] is True
    assert "R1:bbb" not in by_key  # superseded by newer sibling
    assert by_key["R1:ddd"]["fileable"] is False  # watching


def test_r1_skips_superseded_runs() -> None:
    runs = [
        {
            "id": "old",
            "title": "Old fail",
            "status": "failed",
            "created_at_utc": _ts(100),
            "inbox_id": None,
            "superseded_by": "new",
        },
    ]
    assert SWEEP.collect_runs(runs, [], NOW)[0] == []


def test_r1_skips_failed_mentioned_in_open_inbox() -> None:
    runs = [
        {
            "id": "abc12345",
            "title": "Fail",
            "status": "failed",
            "created_at_utc": _ts(100),
            "inbox_id": None,
        },
    ]
    inbox = [
        {
            "id": "i9",
            "title": "Requeue abc12345",
            "status": "open",
            "body": "",
            "resolution": "",
            "note": "",
        },
    ]
    assert SWEEP.collect_runs(runs, inbox, NOW)[0] == []


def test_idle_branch_ready_live_flagged() -> None:
    runs = [
        {"id": "q", "title": "Q", "status": "queued", "created_at_utc": _ts(100)},
        {"id": "b", "title": "B", "status": "branch-ready", "created_at_utc": _ts(100)},
        {"id": "l", "title": "L", "status": "live", "created_at_utc": _ts(20)},
        {"id": "m", "title": "M", "status": "merged", "created_at_utc": _ts(200)},
    ]
    findings, _resolved = SWEEP.collect_runs(runs, [], NOW)
    by_key = {f["key"]: f for f in findings}
    assert by_key["R2:q"]["fileable"] is True
    assert by_key["R3:b"]["fileable"] is True
    assert by_key["R4:l"]["fileable"] is True
    assert not [k for k in by_key if k.startswith("R1:m")]


def test_mtime_fallback_flags_timestamp_less_records(tmp_path: Path) -> None:
    store = tmp_path / "runs"
    store.mkdir()
    (store / "x.json").write_text(
        json.dumps({"id": "x", "title": "X", "status": "live"}), encoding="utf-8"
    )
    runs = SWEEP._load_store(tmp_path, "runs")
    assert runs[0]["_file_mtime"]
    findings, _resolved = SWEEP.collect_runs(runs, [], NOW)
    assert findings[0]["key"] == "R4:x"
    assert findings[0]["fileable"] is False  # just written -> watching


def test_inbox_answered_open_buckets() -> None:
    inbox = [
        {
            "id": "a1",
            "title": "A",
            "status": "answered",
            "assignee": "owner",
            "created_at": _ts(30),
            "answer": "yes",
        },
        {"id": "a2", "title": "B", "status": "open", "assignee": "agent", "created_at": _ts(60)},
        {"id": "a3", "title": "C", "status": "open", "assignee": "owner", "created_at": _ts(60)},
        {"id": "a4", "title": "D", "status": "closed", "created_at": _ts(60)},
    ]
    by_key = {f["key"]: f for f in SWEEP.collect_inbox(inbox, NOW)}
    assert by_key["I1:a1"]["fileable"] is True
    assert by_key["I2:a2"]["fileable"] is True
    assert by_key["I3:a3"]["fileable"] is False  # 7d gate
    assert "I3:a4" not in by_key and "I1:a4" not in by_key


def test_e2e_linkage() -> None:
    tasks = [
        {"id": "t1", "title": "E2E promotion for abc1234", "status": "open", "created_at": _ts(60)},
        {
            "id": "t2",
            "title": "E2E promotion for def5678",
            "status": "submitted",
            "created_at": _ts(60),
        },
    ]
    reports = [
        {
            "id": "r1",
            "title": "E2E promotion for abc1234",
            "overall": "fail",
            "built_utc": _ts(30),
            "commit": "abc1234xy",
        },
        {
            "id": "r2",
            "title": "E2E promotion for 9999999",
            "overall": "fail",
            "built_utc": _ts(30),
            "commit": "9999999zz",
        },
        {
            "id": "r3",
            "title": "E2E promotion for 8888888",
            "overall": "fail",
            "built_utc": _ts(30),
            "commit": "8888888zz",
        },
        {
            "id": "r4",
            "title": "E2E promotion for 7777777",
            "overall": "pass",
            "built_utc": _ts(30),
            "commit": "7777777zz",
        },
    ]
    runs = [
        {"id": "f1", "title": "E2E follow-up: 9999999 (1 failed)", "status": "failed"},
    ]
    findings, _resolved = SWEEP.collect_e2e(tasks, reports, runs, [], NOW)
    by_key = {f["key"]: f for f in findings}
    assert by_key["E1:r1"]["fileable"] is True  # no follow-up anywhere
    assert by_key["E2:r2"]["fileable"] is True  # follow-up failed
    assert "E1:r3" in by_key and by_key["E1:r3"]["fileable"] is True
    assert "E3:t1" in by_key and by_key["E3:t1"]["assignee"] == "owner"
    assert not [k for k in by_key if ":t2" in k or ":r4" in k]


def test_final_e2e_followup_resolves_only_its_linked_report() -> None:
    report = {
        "id": "r1",
        "title": "E2E promotion for abc1234",
        "overall": "fail",
        "built_utc": _ts(30),
        "commit": "abc1234",
    }
    run = {"title": "E2E follow-up: abc1234", "status": "failed"}
    item = {
        "id": "i1",
        "title": "E2E follow-up: abc1234",
        "status": "closed",
        "metadata": {"report_id": "r1"},
        "resolution_kind": "final",
        "resolution": "Verified fixed live.",
    }
    findings, resolved = SWEEP.collect_e2e([], [report], [run], [item], NOW)
    assert findings == []
    assert resolved[0]["inbox_id"] == "i1"
    assert report["overall"] == "fail"
    for change in (
        {"status": "open"},
        {"resolution_kind": "interim"},
        {"resolution": ""},
        {"metadata": {"report_id": "other"}},
    ):
        findings, _ = SWEEP.collect_e2e([], [report], [run], [item | change], NOW)
        assert [f["key"] for f in findings] == ["E2:r1"]


def test_closed_approval_resolves_r1_and_stales_r2() -> None:
    inbox = [
        {
            "id": "i1",
            "title": "Approve: A",
            "status": "closed",
            "created_at": _ts(100),
            "resolution": "underlying task resolved",
        },
        {
            "id": "i2",
            "title": "Approve: B",
            "status": "closed",
            "created_at": _ts(100),
            "resolution": "Superseded: done directly",
        },
    ]
    runs = [
        {
            "id": "f",
            "title": "Failed A",
            "status": "failed",
            "created_at_utc": _ts(100),
            "inbox_id": "i1",
        },
        {
            "id": "q",
            "title": "Queued B",
            "status": "queued",
            "created_at_utc": _ts(100),
            "inbox_id": "i2",
        },
    ]
    findings, resolved = SWEEP.collect_runs(runs, inbox, NOW)
    by_key = {f["key"]: f for f in findings}
    assert "R1:f" not in by_key
    assert "R2:q" not in by_key
    assert {r["key"] for r in resolved} == {"R1:f", "R2:q"}
    r5 = [f for f in findings if f["category"] == "R5"]
    assert len(r5) == 1 and r5[0]["members"][0]["id"] == "q"


def test_still_open_tracker_keeps_finding() -> None:
    inbox = [
        {
            "id": "i1",
            "title": "Approve: A",
            "status": "closed",
            "created_at": _ts(100),
            "resolution": "Partial: task abc12345 stays open for the second half",
        },
        {"id": "abc12345zz", "title": "Second half", "status": "open", "created_at": _ts(90)},
    ]
    runs = [
        {
            "id": "deadbeefdeadbeefdeadbeefdeadbeef",
            "title": "Failed A",
            "status": "failed",
            "created_at_utc": _ts(100),
            "inbox_id": "i1",
        },
    ]
    findings, _resolved = SWEEP.collect_runs(runs, inbox, NOW)
    assert "R1:deadbeefdeadbeefdeadbeefdeadbeef" in {f["key"] for f in findings}


def test_old_run_verify_first_with_evidence() -> None:
    inbox = [
        {
            "id": "i9",
            "title": "Approve: mobile top bar",
            "status": "closed",
            "created_at": _ts(200),
            "resolution": "Merged fix/mobile-topbar",
        },
    ]
    runs = [
        {
            "id": "old",
            "title": "Top bar in mobile",
            "status": "failed",
            "created_at_utc": _ts(200),
            "inbox_id": None,
        },
    ]
    findings, _resolved = SWEEP.collect_runs(runs, inbox, NOW, ("develop", "fix/mobile-topbar"))
    finding = next(f for f in findings if f["key"] == "R1:old")
    assert finding["action"].startswith("VERIFY FIRST")
    member_ids = [m["id"] for m in finding["members"]]
    assert "inbox:i9" in member_ids
    assert "branch:fix/mobile-topbar" in member_ids


def test_e3_skips_superseded_tasks() -> None:
    tasks = [
        {
            "id": "old",
            "title": "E2E promotion for abc",
            "status": "open",
            "created_at": _ts(100),
            "merge_commit": "abc123",
            "items": [{"id": "behavior:x", "behavior": "X"}],
        },
        {
            "id": "new",
            "title": "E2E promotion for abc",
            "status": "open",
            "created_at": _ts(10),
            "merge_commit": "abc123",
            "items": [{"id": "behavior:x", "behavior": "X"}],
        },
    ]
    findings, resolved = SWEEP.collect_e2e(tasks, [], [], [], NOW)
    keys = {f["key"] for f in findings}
    assert "E3:old" not in keys
    assert "E3:new" in keys
    assert {r["key"] for r in resolved} == {"E3:old"}


def test_findings_carry_dashboard_links() -> None:
    runs = [
        {
            "id": "r1",
            "title": "Fail",
            "status": "failed",
            "created_at_utc": _ts(100),
            "inbox_id": None,
        },
    ]
    findings, _resolved = SWEEP.collect_runs(runs, [], NOW)
    assert findings[0]["link"] == ""  # links attach in run(), not collectors
    body = SWEEP._filing_body(
        {
            "key": "E3:t",
            "gate_h": 48,
            "action": "act",
            "members": [],
            "link": "http://127.0.0.1:8766/#/e2e/t",
        },
        "receipt-x.json",
    )
    assert "Open: http://127.0.0.1:8766/#/e2e/t" in body


def test_run_writes_receipt_and_skips(tmp_path: Path) -> None:
    data = tmp_path / "data"
    (data / "runs").mkdir(parents=True)
    (data / "inbox").mkdir()
    (data / "e2e_tasks").mkdir()
    (data / "e2e_reports").mkdir()
    (data / "runs" / "f.json").write_text(
        json.dumps(
            {
                "id": "f",
                "title": "Fail",
                "status": "failed",
                "created_at_utc": _ts(100),
                "inbox_id": None,
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "out"
    receipt = SWEEP.run(data_dir=data, out_dir=out, repo=tmp_path, skip_keys=frozenset({"R1:f"}))
    assert receipt["counts"]["findings"] == 1
    assert receipt["counts"]["skipped_manual"] == 1
    assert receipt["counts"]["fileable_new"] == 0
    assert (out / receipt["receipt"]).exists()


def test_r1_skips_run_with_prior_sweep_resolution() -> None:
    runs = [
        {
            "id": "e84ef642012f42e9929e6fc1ea3e6480",
            "title": "Top bar in mobile",
            "status": "failed",
            "created_at_utc": _ts(100),
            "inbox_id": None,
            "error": "stuck",
        }
    ]
    inbox = [
        {
            "id": "6c233cc6e11d4884bddb71aa310dcc6b",
            "title": "[sweep] Failed run with no follow-up: Top bar in mobile",
            "status": "closed",
            "body": "Members: e84ef642012f42e9929e6fc1ea3e6480",
            "resolution": "Resolved-first confirmed: fixed by merged branch.",
        }
    ]
    findings, resolved = SWEEP.collect_runs(runs, inbox, NOW)
    assert findings == []
    assert [r["key"] for r in resolved] == ["R1:e84ef642012f42e9929e6fc1ea3e6480"]


def test_r1_still_files_when_prior_resolution_tracks_open_work() -> None:
    runs = [
        {
            "id": "abc123",
            "title": "Old fail",
            "status": "failed",
            "created_at_utc": _ts(100),
            "inbox_id": None,
            "error": "boom",
        }
    ]
    inbox = [
        {
            "id": "sweep1",
            "title": "[sweep] Failed run with no follow-up: Old fail",
            "status": "closed",
            "body": "abc123",
            "resolution": "Tracked elsewhere, still open, see tracker abcdef123456.",
        },
        {"id": "abcdef1234567890", "title": "Tracker", "status": "open"},
    ]
    findings, _resolved = SWEEP.collect_runs(runs, inbox, NOW)
    assert [f["key"] for f in findings] == ["R1:abc123"]


def _report(rid, commit, overall, hours_ago):
    return {
        "id": rid,
        "title": f"E2E promotion for {commit}",
        "commit": commit,
        "overall": overall,
        "built_utc": _ts(hours_ago),
    }


def test_e1_skips_fail_covered_by_newer_pass() -> None:
    reports = [
        _report("old-fail", "d16ed73", "fail", 20),
        _report("new-pass", "d16ed73", "pass", 2),
    ]
    findings, resolved = SWEEP.collect_e2e([], reports, [], [], NOW)
    assert findings == []
    assert [r["key"] for r in resolved] == ["E1:old-fail"]


def test_e1_still_files_when_pass_predates_fail() -> None:
    reports = [
        _report("old-pass", "d16ed73", "pass", 20),
        _report("new-fail", "d16ed73", "fail", 2),
    ]
    findings, _resolved = SWEEP.collect_e2e([], reports, [], [], NOW)
    assert [f["key"] for f in findings] == ["E1:new-fail"]


def _git_repo_with_remote(tmp_path: Path):
    import subprocess

    def git(*args: str, cwd: Path | None = None) -> str:
        completed = subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
            cwd=cwd or tmp_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert completed.returncode == 0, completed.stderr
        return completed.stdout.strip()

    remote = tmp_path / "remote"
    repo = tmp_path / "repo"
    git("init", "--bare", "-q", str(remote))
    git("init", "-q", "-b", "develop", str(repo))
    (repo / "f.txt").write_text("one", encoding="utf-8")
    git("add", ".", cwd=repo)
    git("commit", "-qm", "one", cwd=repo)
    git("remote", "add", "origin", str(remote), cwd=repo)
    git("push", "-q", "origin", "develop", cwd=repo)
    return repo


def _write_serve_version(repo: Path, commit: str) -> None:
    target = repo / "apps" / "workbench_dashboard" / "data" / "serve-version.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"commit": commit}), encoding="utf-8")


def test_g4_flags_serve_lagging_origin(tmp_path: Path) -> None:
    import subprocess

    def git(*args: str, cwd: Path) -> str:
        completed = subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert completed.returncode == 0, completed.stderr
        return completed.stdout.strip()

    repo = _git_repo_with_remote(tmp_path)
    old = git("rev-parse", "HEAD", cwd=repo)
    _write_serve_version(repo, old)
    (repo / "f.txt").write_text("two", encoding="utf-8")
    git("add", ".", cwd=repo)
    git("commit", "-qm", "two", cwd=repo)
    git("push", "-q", "origin", "develop", cwd=repo)
    findings = SWEEP.collect_git(repo, tmp_path / "runs", NOW)
    assert [f["key"] for f in findings if f["key"].startswith("G4")] != []
    _write_serve_version(repo, git("rev-parse", "HEAD", cwd=repo))
    findings = SWEEP.collect_git(repo, tmp_path / "runs", NOW)
    assert [f["key"] for f in findings if f["key"].startswith("G4")] == []


def test_g4_skips_missing_version_file(tmp_path: Path) -> None:
    repo = _git_repo_with_remote(tmp_path)
    findings = SWEEP.collect_git(repo, tmp_path / "runs", NOW)
    assert [f["key"] for f in findings if f["key"].startswith("G4")] == []


def test_i4_flags_agent_item_idle_after_terminal_run() -> None:
    inbox = [
        {
            "id": "stale",
            "title": "Follow-up",
            "status": "open",
            "assignee": "agent",
            "created_at": _ts(60),
            "metadata": {"bridge_run_id": "r-done"},
        },
        {
            "id": "live",
            "title": "Working",
            "status": "open",
            "assignee": "agent",
            "created_at": _ts(60),
            "metadata": {"bridge_run_id": "r-run"},
        },
        {
            "id": "unlinked",
            "title": "No run",
            "status": "open",
            "assignee": "agent",
            "created_at": _ts(60),
        },
    ]
    runs = [
        {"id": "r-done", "status": "completed", "finished_at_utc": _ts(30)},
        {"id": "r-run", "status": "queued"},
    ]
    findings = SWEEP.collect_inbox(inbox, NOW, runs)
    assert [f["key"] for f in findings if f["key"].startswith("I4")] == ["I4:stale"]
    stale = next(f for f in findings if f["key"] == "I4:stale")
    assert stale["fileable"] is True
    assert "completed" in stale["title"]
    assert SWEEP.collect_inbox(inbox, NOW) == [f for f in findings if not f["key"].startswith("I4")]


def test_flags_needs_attention_runs() -> None:
    runs = [
        {
            "id": "na1",
            "title": "Hollow finish",
            "status": "needs-attention",
            "created_at_utc": _ts(100),
            "inbox_id": None,
            "error": "completed but the report is hollow",
        },
    ]
    findings, _resolved = SWEEP.collect_runs(runs, [], NOW)
    by_key = {f["key"]: f for f in findings}
    assert by_key["R1:na1"]["fileable"] is True


def test_i5_files_uncovered_owner_gates() -> None:
    gates = [
        {
            "id": "g1",
            "title": "Gate one",
            "body": "Decide X.",
            "type": "decision",
            "options": ["A", "B"],
        },
        {"id": "g2", "title": "Gate two", "body": "Do Y.", "type": "task", "options": ["Done"]},
    ]
    inbox = [
        {
            "id": "covered",
            "title": "Gate one",
            "status": "open",
            "assignee": "owner",
            "created_at_utc": _ts(5),
            "metadata": {"owner_gate": "g1"},
        },
        {
            "id": "shut",
            "title": "Gate two",
            "status": "closed",
            "assignee": "owner",
            "created_at_utc": _ts(50),
            "metadata": {"owner_gate": "g2"},
        },
    ]
    findings = SWEEP.collect_inbox(inbox, NOW, [], gates)
    by_key = {f["key"]: f for f in findings if f["key"].startswith("I5:")}
    assert by_key == {}  # open covers g1; closed-with-record covers g2
    del inbox[1]
    gates.append(
        {"id": "g3", "title": "Gate three", "body": "Do Z.", "type": "task", "options": ["Done"]}
    )
    findings = SWEEP.collect_inbox(inbox, NOW, [], gates)
    by_key = {f["key"]: f for f in findings if f["key"].startswith("I5:")}
    assert set(by_key) == {"I5:g2", "I5:g3"}  # missing items re-file
    assert by_key["I5:g2"]["fileable"] is True
    assert by_key["I5:g2"]["assignee"] == "owner"
    assert by_key["I5:g2"]["gate_body"] == "Do Y."
    assert SWEEP.collect_inbox([], NOW, [], None) == [
        f for f in SWEEP.collect_inbox([], NOW, []) if not f["key"].startswith("I5:")
    ]


def test_r3_flags_lost_staged_branch(tmp_path: Path) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    subprocess.run(["git", "branch", "live-branch"], cwd=tmp_path, check=True)
    runs = [
        {
            "id": "gone",
            "title": "Lost work",
            "status": "branch-ready",
            "created_at_utc": _ts(100),
            "branch": "deleted-branch",
            "commit": "deadbee",
        },
        {
            "id": "here",
            "title": "Live work",
            "status": "branch-ready",
            "created_at_utc": _ts(100),
            "branch": "live-branch",
        },
    ]
    findings, _resolved = SWEEP.collect_runs(runs, [], NOW, (), tmp_path)
    by_key = {f["key"]: f for f in findings}
    assert "lost staged branch" in by_key["R3:gone"]["title"]
    assert "close the run record" in by_key["R3:gone"]["action"]
    assert by_key["R3:gone"]["fileable"] is True
    assert "awaiting merge" in by_key["R3:here"]["title"]

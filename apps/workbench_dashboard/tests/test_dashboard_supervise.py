"""Redeploy supervisor: decisions, markers, version/maintenance endpoints."""

from __future__ import annotations

import json
import sys
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parent.parent
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from dashboard_supervise import (  # noqa: E402
    SuperviseConfig,
    _pid_start_time,
    _pidfile_matches_process,
    decide,
    restart_dashboard,
    write_maintenance,
    write_serve_version,
)


def test_decide_matrix() -> None:
    assert decide(running_commit="a", origin_commit="a")[0] == "up-to-date"
    assert decide(running_commit="a", origin_commit="b")[0] == "redeploy"
    assert decide(running_commit=None, origin_commit="b")[0] == "redeploy"
    assert decide(running_commit="a", origin_commit=None)[0] == "skip-unknown"
    assert decide(running_commit=None, origin_commit=None)[0] == "skip-unknown"
    assert decide(running_commit="ce41866", origin_commit="ce41866ad3c4de81")[0] == "up-to-date"


def test_maintenance_round_trip(tmp_path) -> None:
    from dashboard_web_app import read_maintenance

    assert read_maintenance(tmp_path) == {"active": False}
    write_maintenance(tmp_path, active=True, message="updating")
    marker = read_maintenance(tmp_path)
    assert marker["active"] is True and marker["message"] == "updating"
    assert marker["since_utc"]
    write_maintenance(tmp_path, active=False)
    assert read_maintenance(tmp_path)["active"] is False
    (tmp_path / "maintenance.json").write_text("not json", encoding="utf-8")
    assert read_maintenance(tmp_path) == {"active": False}


def test_serve_version_prefers_file_over_git(tmp_path, monkeypatch) -> None:
    from dashboard_web_app import capture_server_version

    write_serve_version(tmp_path, branch="develop", commit="abc1234")
    info = capture_server_version(Path("."), data_dir=tmp_path)
    assert (info["branch"], info["commit"]) == ("develop", "abc1234")
    assert info["started_utc"]


def test_serve_version_carries_commit_timestamp(tmp_path) -> None:
    import json

    from dashboard_web_app import capture_server_version

    write_serve_version(
        tmp_path, branch="develop", commit="abc1234", commit_utc="2026-11-13T12:00:00+00:00"
    )
    filed = json.loads((tmp_path / "serve-version.json").read_text(encoding="utf-8"))
    assert filed["commit_utc"] == "2026-11-13T12:00:00+00:00"
    info = capture_server_version(Path("."), data_dir=tmp_path)
    assert info["commit_utc"] == "2026-11-13T12:00:00+00:00"


def test_capture_version_reads_commit_date_from_git(tmp_path) -> None:
    import subprocess

    from dashboard_web_app import capture_server_version

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True)
    info = capture_server_version(tmp_path)
    expect = subprocess.run(
        ["git", "show", "-s", "--format=%cI", "HEAD"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert info["commit_utc"] == expect


def test_version_endpoint_serves_snapshot(dashboard_server, monkeypatch) -> None:
    from dashboard_test_http import get_json
    from dashboard_web_app import DashboardRequestHandler

    monkeypatch.setattr(
        DashboardRequestHandler,
        "served_version",
        {"branch": "develop", "commit": "abc1234", "tier": "tooling"},
        raising=False,
    )
    payload = get_json(dashboard_server, "/api/version")
    assert payload["ok"] is True
    assert (payload["branch"], payload["commit"]) == ("develop", "abc1234")


def test_maintenance_endpoint_defaults_inactive(dashboard_server) -> None:
    from dashboard_test_http import get_json

    payload = get_json(dashboard_server, "/api/maintenance")
    assert payload["ok"] is True and payload["active"] is False


def test_dry_run_tick_never_touches_tree(tmp_path, monkeypatch) -> None:
    import dashboard_supervise as sup

    monkeypatch.setattr(sup, "read_origin_commit", lambda *a: "b" * 40)
    monkeypatch.setattr(sup, "read_served_commit", lambda *a: "a" * 40)
    config = sup.SuperviseConfig(
        main_root=tmp_path,
        worktree=tmp_path / "wt",
        data_dir=tmp_path / "data",
        config_path=tmp_path / "dashboard.json",
        port=8766,
        serve_branch="develop",
        python_exe="python",
    )
    outcome = sup.supervise_tick(config, dry_run=True)
    assert outcome["action"] == "redeploy"
    assert outcome["dry_run"] is True
    assert not (tmp_path / "wt").exists()
    assert not (tmp_path / "data" / "maintenance.json").exists()


def test_tick_reports_up_to_date_without_side_effects(tmp_path, monkeypatch) -> None:
    import dashboard_supervise as sup

    monkeypatch.setattr(sup, "read_origin_commit", lambda *a: "a" * 40)
    monkeypatch.setattr(sup, "read_served_commit", lambda *a: "a" * 40)
    config = sup.SuperviseConfig(
        main_root=tmp_path,
        worktree=tmp_path / "wt",
        data_dir=tmp_path / "data",
        config_path=tmp_path / "dashboard.json",
        port=8766,
        serve_branch="develop",
        python_exe="python",
    )
    outcome = sup.supervise_tick(config)
    assert outcome["action"] == "up-to-date"
    assert not (tmp_path / "wt").exists()


def test_target_gate_requires_repo_root_flag(tmp_path) -> None:
    import subprocess

    from dashboard_supervise import target_supports_worktree

    repo = tmp_path / "repo"
    app = repo / "apps" / "workbench_dashboard"
    app.mkdir(parents=True)
    (app / "dashboard_web_app.py").write_text("plain = True\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "old"],
        cwd=repo,
        check=True,
    )
    old = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert target_supports_worktree(repo, old) is False
    (app / "dashboard_web_app.py").write_text("--repo-root support\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "new"],
        cwd=repo,
        check=True,
    )
    new = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert target_supports_worktree(repo, new) is True


def test_tick_skips_unknown_origin(tmp_path, monkeypatch) -> None:
    import dashboard_supervise as sup

    monkeypatch.setattr(sup, "read_origin_commit", lambda *a: None)
    monkeypatch.setattr(sup, "read_served_commit", lambda *a: "a" * 40)
    config = sup.SuperviseConfig(
        main_root=tmp_path,
        worktree=tmp_path / "wt",
        data_dir=tmp_path / "data",
        config_path=tmp_path / "dashboard.json",
        port=8766,
        serve_branch="develop",
        python_exe="python",
    )
    assert sup.supervise_tick(config)["action"] == "skip-unknown"


def test_config_accepts_tier_and_branch(tmp_path) -> None:
    from dashboard_config import load_config

    path = tmp_path / "dashboard.json"
    assert load_config(path).product_tier == "tooling"
    path.write_text(
        json.dumps({"product_tier": "commercial", "serve_branch": "main"}), encoding="utf-8"
    )
    config = load_config(path)
    assert (config.product_tier, config.serve_branch) == ("commercial", "main")
    path.write_text(json.dumps({"product_tier": "enterprise"}), encoding="utf-8")
    try:
        load_config(path)
    except ValueError as exc:
        assert "product_tier" in str(exc)
    else:
        raise AssertionError("bad tier accepted")


def test_js_banner_pill_and_poller_present() -> None:
    js = (DASHBOARD_DIR / "web" / "app.js").read_text(encoding="utf-8")
    html = (DASHBOARD_DIR / "web" / "index.html").read_text(encoding="utf-8")
    assert 'id="maint-banner"' in html
    assert 'id="version-pill"' in html
    assert "startMaintPoll()" in js
    assert "loadVersionPill()" in js
    assert "/api/maintenance" in js
    assert "/api/version" in js


def test_pid_start_time_matches_live_process() -> None:
    import os
    import time

    started = _pid_start_time(os.getpid())
    assert started is not None
    assert abs(started - time.time()) < 86400


def test_pid_start_time_unknown_for_dead_pid() -> None:
    assert _pid_start_time(99999999) is None


def test_pidfile_match_rejects_recycled_and_garbage() -> None:
    import os
    from datetime import UTC, datetime

    live = {"pid": os.getpid(), "started_utc": datetime.now(UTC).isoformat()}
    assert _pidfile_matches_process(live, os.getpid()) is True
    stale = {"pid": os.getpid(), "started_utc": "2001-01-01T00:00:00+00:00"}
    assert _pidfile_matches_process(stale, os.getpid()) is False
    assert _pidfile_matches_process({"pid": os.getpid()}, os.getpid()) is False
    assert (
        _pidfile_matches_process({"pid": 99999999, "started_utc": live["started_utc"]}, 99999999)
        is False
    )


def _supervise_config(tmp_path: Path) -> SuperviseConfig:
    (tmp_path / "apps" / "workbench_dashboard").mkdir(parents=True)
    return SuperviseConfig(
        main_root=tmp_path,
        worktree=tmp_path,
        data_dir=tmp_path / "data",
        config_path=tmp_path / "dashboard.json",
        port=8766,
        serve_branch="develop",
        python_exe="python",
    )


def test_restart_escalates_to_sigterm_on_tracked_server(tmp_path, monkeypatch) -> None:
    import os
    import signal
    import subprocess
    import types
    from datetime import UTC, datetime

    import dashboard_supervise as sup

    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "dashboard.pid").write_text(
        json.dumps({"pid": os.getpid(), "started_utc": datetime.now(UTC).isoformat()}),
        encoding="utf-8",
    )
    signals: list = []

    def fake_kill(pid, sig):
        signals.append(sig)
        if sig == signal.SIGTERM:
            raise ProcessLookupError(pid)

    monkeypatch.setattr(os, "kill", fake_kill)
    busy = iter([True, False])
    monkeypatch.setattr(sup, "_port_busy", lambda port: next(busy, False))
    monkeypatch.setattr(sup, "PORT_FREE_TIMEOUT_SECONDS", 0)
    monkeypatch.setattr(sup, "_port_listeners", lambda port: [])
    monkeypatch.setattr(sup, "_python_pids", lambda: [])
    monkeypatch.setattr(
        sup,
        "_probe_cmdlines",
        lambda pids: {
            os.getpid(): "C:\\venv\\python.exe dashboard_web_app.py --port 8766 --repo-root C:\\ai-workbench"
        },
    )
    spawned: list = []
    monkeypatch.setattr(
        subprocess, "Popen", lambda *a, **k: spawned.append(42) or types.SimpleNamespace(pid=4242)
    )
    ok, _detail = restart_dashboard(_supervise_config(tmp_path))
    assert ok is True
    assert signals == [signal.SIGINT, signal.SIGTERM]
    assert len(spawned) == 1


def _mail_throttle_config(tmp_path: Path) -> SuperviseConfig:
    (tmp_path / "data").mkdir(exist_ok=True)
    return SuperviseConfig(
        main_root=tmp_path,
        worktree=tmp_path / "wt",
        data_dir=tmp_path / "data",
        config_path=tmp_path / "dashboard.json",
        port=8766,
        serve_branch="develop",
        python_exe="python",
    )


def _stub_redeploy_pipeline(monkeypatch, *, restart_result: tuple) -> list:
    """Force a redeploy attempt; return the list recording _mail_failure calls."""
    import dashboard_supervise as sup

    monkeypatch.setattr(sup, "read_origin_commit", lambda *a: "b" * 40)
    monkeypatch.setattr(sup, "read_served_commit", lambda *a: "a" * 40)
    monkeypatch.setattr(sup, "target_supports_worktree", lambda *a: True)
    monkeypatch.setattr(sup, "ensure_worktree", lambda *a: (True, "ok"))
    monkeypatch.setattr(sup, "sync_worktree", lambda *a: ("c" * 40, "synced"))
    monkeypatch.setattr(sup, "restart_dashboard", lambda *a: restart_result)
    monkeypatch.setattr(sup, "wait_healthy", lambda *a: True)
    mailed: list = []
    monkeypatch.setattr(sup, "_mail_failure", lambda config, reason: mailed.append(reason))
    return mailed


def test_first_failure_mails(tmp_path, monkeypatch) -> None:
    import dashboard_supervise as sup

    mailed = _stub_redeploy_pipeline(monkeypatch, restart_result=(False, "boom"))
    outcome = sup.supervise_tick(_mail_throttle_config(tmp_path))
    assert outcome["action"] == "failed"
    assert mailed == ["boom"]


def test_identical_repeat_failure_does_not_remail(tmp_path, monkeypatch) -> None:
    import dashboard_supervise as sup

    mailed = _stub_redeploy_pipeline(monkeypatch, restart_result=(False, "boom"))
    config = _mail_throttle_config(tmp_path)
    assert sup.supervise_tick(config)["action"] == "failed"
    assert sup.supervise_tick(config)["action"] == "failed"
    assert sup.supervise_tick(config)["action"] == "failed"
    assert mailed == ["boom"]


def test_changed_reason_mails_again(tmp_path, monkeypatch) -> None:
    import dashboard_supervise as sup

    mailed = _stub_redeploy_pipeline(monkeypatch, restart_result=(False, "boom"))
    config = _mail_throttle_config(tmp_path)
    assert sup.supervise_tick(config)["action"] == "failed"
    monkeypatch.setattr(sup, "restart_dashboard", lambda *a: (False, "different"))
    assert sup.supervise_tick(config)["action"] == "failed"
    assert mailed == ["boom", "different"]


def test_recovery_then_refail_mails_again(tmp_path, monkeypatch) -> None:
    import dashboard_supervise as sup

    mailed = _stub_redeploy_pipeline(monkeypatch, restart_result=(False, "boom"))
    config = _mail_throttle_config(tmp_path)
    assert sup.supervise_tick(config)["action"] == "failed"
    monkeypatch.setattr(sup, "restart_dashboard", lambda *a: (True, "respawned"))
    assert sup.supervise_tick(config)["action"] == "redeployed"
    monkeypatch.setattr(sup, "restart_dashboard", lambda *a: (False, "boom"))
    assert sup.supervise_tick(config)["action"] == "failed"
    assert mailed == ["boom", "boom"]


def test_up_to_date_clears_mailed_incident(tmp_path, monkeypatch) -> None:
    import dashboard_supervise as sup

    mailed = _stub_redeploy_pipeline(monkeypatch, restart_result=(False, "boom"))
    config = _mail_throttle_config(tmp_path)
    assert sup.supervise_tick(config)["action"] == "failed"
    monkeypatch.setattr(sup, "read_origin_commit", lambda *a: "a" * 40)
    assert sup.supervise_tick(config)["action"] == "up-to-date"
    monkeypatch.setattr(sup, "read_origin_commit", lambda *a: "b" * 40)
    assert sup.supervise_tick(config)["action"] == "failed"
    assert mailed == ["boom", "boom"]


def test_restart_refuses_strangers_without_signals(tmp_path, monkeypatch) -> None:
    import os
    import subprocess

    import dashboard_supervise as sup

    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "dashboard.pid").write_text(
        json.dumps({"pid": os.getpid(), "started_utc": "2001-01-01T00:00:00+00:00"}),
        encoding="utf-8",
    )
    signals: list = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: signals.append(sig))
    monkeypatch.setattr(sup, "_port_busy", lambda port: True)
    monkeypatch.setattr(sup, "_port_listeners", lambda port: [999])
    monkeypatch.setattr(sup, "_python_pids", lambda: [])
    monkeypatch.setattr(sup, "_probe_cmdlines", lambda pids: {999: "evil.exe --port 8766"})
    spawned: list = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: spawned.append(a))
    ok, detail = restart_dashboard(_supervise_config(tmp_path))
    assert ok is False
    assert "strangers=[999]" in detail
    assert "refusing to kill strangers" in detail
    assert signals == []
    assert spawned == []


def test_restart_refuses_unidentifiable_holders(tmp_path, monkeypatch) -> None:
    import os
    import subprocess

    import dashboard_supervise as sup

    (tmp_path / "data").mkdir()
    signals: list = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: signals.append(sig))
    monkeypatch.setattr(sup, "_port_busy", lambda port: True)
    monkeypatch.setattr(sup, "_port_listeners", lambda port: [999])
    monkeypatch.setattr(sup, "_python_pids", lambda: [])
    monkeypatch.setattr(sup, "_probe_cmdlines", lambda pids: {})
    spawned: list = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: spawned.append(a))
    ok, detail = restart_dashboard(_supervise_config(tmp_path))
    assert ok is False
    assert "unknown=[999]" in detail
    assert signals == []
    assert spawned == []


def test_restart_kills_every_verified_duplicate(tmp_path, monkeypatch) -> None:
    import os
    import signal
    import subprocess
    import time
    import types

    import dashboard_supervise as sup

    (tmp_path / "data").mkdir()
    ours_cmdline = (
        "C:\\repo\\.venv\\Scripts\\python.exe dashboard_web_app.py "
        "--host 127.0.0.1 --port 8766 --repo-root C:\\repo\\ai-workbench"
    )
    monkeypatch.setattr(sup, "_port_listeners", lambda port: [111, 222])
    monkeypatch.setattr(sup, "_python_pids", lambda: [])
    monkeypatch.setattr(sup, "_probe_cmdlines", lambda pids: {111: ours_cmdline, 222: ours_cmdline})
    monkeypatch.setattr(sup, "_pid_start_time", lambda pid: time.time())
    monkeypatch.setattr(sup, "PORT_FREE_TIMEOUT_SECONDS", 0)
    busy = iter([True, False])
    monkeypatch.setattr(sup, "_port_busy", lambda port: next(busy, False))
    signals: list = []

    def fake_kill(pid, sig):
        signals.append((pid, sig))
        raise ProcessLookupError(pid)

    monkeypatch.setattr(os, "kill", fake_kill)
    spawned: list = []
    monkeypatch.setattr(
        subprocess, "Popen", lambda *a, **k: spawned.append(42) or types.SimpleNamespace(pid=4242)
    )
    ok, detail = restart_dashboard(_supervise_config(tmp_path))
    assert ok is True
    assert (111, signal.SIGINT) in signals
    assert (222, signal.SIGINT) in signals
    assert len(spawned) == 1
    assert "pid=4242" in detail


def test_stop_escalates_past_sigint_oserror(monkeypatch) -> None:
    import os
    import signal
    import time

    import dashboard_supervise as sup

    signals: list = []

    def fake_kill(pid, sig):
        signals.append(sig)
        if sig == signal.SIGINT:
            raise OSError("GenerateConsoleCtrlEvent failed")

    monkeypatch.setattr(os, "kill", fake_kill)
    monkeypatch.setattr(sup, "_pid_start_time", lambda pid: time.time())
    monkeypatch.setattr(sup, "PORT_FREE_TIMEOUT_SECONDS", 0)
    survivors = sup._stop_verified_servers({1234: time.time()}, 8766)
    assert signals == [signal.SIGINT, signal.SIGTERM]
    assert survivors == [1234]


def test_restart_names_survivors_when_stop_fails(tmp_path, monkeypatch) -> None:
    import os
    import signal
    import subprocess
    import time

    import dashboard_supervise as sup

    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "dashboard.pid").write_text(
        json.dumps({"pid": 4242, "started_utc": "2026-11-13T00:00:00+00:00"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(sup, "_pidfile_matches_process", lambda record, pid: True)
    monkeypatch.setattr(sup, "_port_listeners", lambda port: [])
    monkeypatch.setattr(sup, "_python_pids", lambda: [])
    monkeypatch.setattr(
        sup,
        "_probe_cmdlines",
        lambda pids: {4242: "python dashboard_web_app.py --port 8766 C:\\ai-workbench"},
    )
    monkeypatch.setattr(sup, "_pid_start_time", lambda pid: time.time())
    signals: list = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: signals.append(sig))
    monkeypatch.setattr(sup, "_port_busy", lambda port: True)
    monkeypatch.setattr(sup, "PORT_FREE_TIMEOUT_SECONDS", 0)
    spawned: list = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: spawned.append(a))
    ok, detail = restart_dashboard(_supervise_config(tmp_path))
    assert ok is False
    assert "survivors=[4242]" in detail
    assert signals == [signal.SIGINT, signal.SIGTERM]
    assert spawned == []


def test_stop_treats_missing_process_as_stopped(monkeypatch) -> None:
    import os
    import signal
    import time

    import dashboard_supervise as sup

    signals: list = []

    def fake_kill(pid, sig):
        signals.append(sig)
        raise ProcessLookupError(pid)

    monkeypatch.setattr(os, "kill", fake_kill)
    monkeypatch.setattr(sup, "_pid_start_time", lambda pid: time.time())
    monkeypatch.setattr(sup, "PORT_FREE_TIMEOUT_SECONDS", 0)
    survivors = sup._stop_verified_servers({1234: time.time()}, 8766)
    assert signals == [signal.SIGINT]
    assert survivors == []


def test_restart_adopts_stuck_non_holder(tmp_path, monkeypatch) -> None:
    import os
    import signal
    import subprocess
    import time
    import types

    import dashboard_supervise as sup

    (tmp_path / "data").mkdir()
    ours_cmdline = "C:\\repo\\.venv\\Scripts\\python.exe dashboard_web_app.py --port 8766 C:\\repo\\ai-workbench"
    monkeypatch.setattr(sup, "_port_listeners", lambda port: [111])
    monkeypatch.setattr(sup, "_python_pids", lambda: [111, 222])
    monkeypatch.setattr(sup, "_probe_cmdlines", lambda pids: {111: ours_cmdline, 222: ours_cmdline})
    monkeypatch.setattr(sup, "_pid_start_time", lambda pid: time.time())
    monkeypatch.setattr(sup, "PORT_FREE_TIMEOUT_SECONDS", 0)
    busy = iter([True, False])
    monkeypatch.setattr(sup, "_port_busy", lambda port: next(busy, False))
    signals: list = []

    def fake_kill(pid, sig):
        signals.append((pid, sig))
        raise ProcessLookupError(pid)

    monkeypatch.setattr(os, "kill", fake_kill)
    spawned: list = []
    monkeypatch.setattr(
        subprocess, "Popen", lambda *a, **k: spawned.append(42) or types.SimpleNamespace(pid=4242)
    )
    ok, _detail = restart_dashboard(_supervise_config(tmp_path))
    assert ok is True
    assert (111, signal.SIGINT) in signals
    assert (222, signal.SIGINT) in signals
    assert len(spawned) == 1


def test_unrelated_pythons_never_wedge_restart(tmp_path, monkeypatch) -> None:
    import subprocess
    import types

    import dashboard_supervise as sup

    (tmp_path / "data").mkdir()
    monkeypatch.setattr(sup, "_port_listeners", lambda port: [])
    monkeypatch.setattr(sup, "_python_pids", lambda: [777])
    monkeypatch.setattr(sup, "_probe_cmdlines", lambda pids: {777: "pytest -q"})
    busy = iter([True, False])
    monkeypatch.setattr(sup, "_port_busy", lambda port: next(busy, False))
    spawned: list = []
    monkeypatch.setattr(
        subprocess, "Popen", lambda *a, **k: spawned.append(42) or types.SimpleNamespace(pid=4242)
    )
    ok, _detail = restart_dashboard(_supervise_config(tmp_path))
    assert ok is True
    assert len(spawned) == 1


def test_python_pids_parses_tasklist(monkeypatch) -> None:
    import subprocess
    import types

    import dashboard_supervise as sup

    out = (
        '"python.exe","13700","Console","1","45,000 K"\r\n'
        '"python.exe","14456","Console","1","46,000 K"\r\n'
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: types.SimpleNamespace(returncode=0, stdout=out),
    )
    assert sup._python_pids() == [13700, 14456]


def test_port_listeners_parses_netstat(monkeypatch) -> None:
    import subprocess
    import types

    import dashboard_supervise as sup

    out = (
        "Active Connections\r\n"
        "  Proto  Local Address          Foreign Address        State           PID\r\n"
        "  TCP    127.0.0.1:8766         0.0.0.0:0              LISTENING       13700\r\n"
        "  TCP    127.0.0.1:8766         0.0.0.0:0              LISTENING       14456\r\n"
        "  TCP    127.0.0.1:8000         0.0.0.0:0              LISTENING       999\r\n"
        "  TCP    127.0.0.1:8766         127.0.0.1:50000        ESTABLISHED     13700\r\n"
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: types.SimpleNamespace(returncode=0, stdout=out),
    )
    assert sup._port_listeners(8766) == [13700, 14456]


def test_cmdline_verdicts() -> None:
    import dashboard_supervise as sup

    ours = "C:\\r\\.venv\\Scripts\\python.exe dashboard_web_app.py --port 8766 --repo-root C:\\r\\ai-workbench"
    assert sup._cmdline_is_ours(ours, 8766) is True
    assert sup._cmdline_is_ours("evil.exe --port 8766", 8766) is False
    assert sup._cmdline_is_ours(ours, 9999) is False
    assert sup._cmdline_is_ours("", 8766) is False


def test_tick_lock_serializes(tmp_path) -> None:
    import dashboard_supervise as sup

    data = tmp_path / "data"
    first = sup._TickLock(data)
    assert first.__enter__() is True
    try:
        second = sup._TickLock(data)
        assert second.__enter__() is False
    finally:
        first.__exit__()


def test_supervise_tick_busy_on_lock_contention(tmp_path, monkeypatch) -> None:
    import dashboard_supervise as sup

    data = tmp_path / "data"
    data.mkdir()
    lock = sup._TickLock(data)
    assert lock.__enter__() is True
    try:
        outcome = sup.supervise_tick(_mail_throttle_config(tmp_path))
    finally:
        lock.__exit__()
    assert outcome["action"] == "busy"


def test_ensure_single_server_refuses_busy_port() -> None:
    import pytest
    from dashboard_web_app import ensure_single_server

    with pytest.raises(SystemExit):
        ensure_single_server("127.0.0.1", 8766, probe=lambda host, port: True)
    ensure_single_server("127.0.0.1", 8766, probe=lambda host, port: False)

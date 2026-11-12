"""Redeploy supervisor: decisions, markers, version/maintenance endpoints."""

from __future__ import annotations

import json
import sys
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parent.parent
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from dashboard_supervise import (  # noqa: E402
    decide,
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

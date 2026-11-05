from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from ai_agent.staged_edits import digest, root_id, stage_file
from dashboard_config import load_config
from dashboard_web_app import DashboardRequestHandler


@pytest.fixture
def project_server(tmp_path, monkeypatch):
    config_path = tmp_path / "dashboard.json"
    config_path.write_text(
        json.dumps({"provider": "ollama", "model": "fake", "title": "Test Board"}),
        encoding="utf-8",
    )
    data_dir = tmp_path / "data"

    class TestHandler(DashboardRequestHandler):
        def log_message(self, format, *args):
            return

    TestHandler.config_path = config_path
    TestHandler.data_dir = data_dir
    TestHandler.repo_root = tmp_path
    server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", tmp_path
    finally:
        server.shutdown()
        server.server_close()


def get_json(base: str, path: str) -> dict:
    with urlopen(f"{base}{path}", timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(base: str, path: str, payload: dict) -> dict:
    request = Request(
        f"{base}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _set_roots(tmp_path: Path, roots: list[str]) -> None:
    (tmp_path / "dashboard.json").write_text(
        json.dumps({"provider": "ollama", "model": "fake", "work_roots": roots}),
        encoding="utf-8",
    )


def _make_project(tmp_path: Path, name: str = "client-a") -> Path:
    project = tmp_path / name
    (project / "src").mkdir(parents=True)
    (project / "src" / "main.py").write_text("old\n", encoding="utf-8")
    return project


def _write_run(tmp_path: Path, run_id: str, record: dict) -> None:
    runs_dir = tmp_path / "data" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / f"{run_id}.json").write_text(json.dumps(record), encoding="utf-8")


def _read_run(tmp_path: Path, run_id: str) -> dict:
    return json.loads((tmp_path / "data" / "runs" / f"{run_id}.json").read_text(encoding="utf-8"))


def _new_session(base: str) -> str:
    created = post_json(base, "/api/chat/sessions", {"title": "Wake me"})
    assert created["ok"] is True
    return created["id"]


# --- config carrier ---


def test_config_defaults_to_no_project_access(tmp_path: Path) -> None:
    config = load_config(tmp_path / "missing.json")
    assert config.work_roots == ()


def test_config_parses_work_roots_as_strings(tmp_path: Path) -> None:
    path = tmp_path / "dashboard.json"
    path.write_text(json.dumps({"work_roots": ["/tmp/a", "/tmp/b"]}), encoding="utf-8")
    assert load_config(path).work_roots == ("/tmp/a", "/tmp/b")
    path.write_text(json.dumps({"work_roots": "/tmp/a"}), encoding="utf-8")
    with pytest.raises(ValueError, match="work_roots"):
        load_config(path)
    path.write_text(json.dumps({"work_roots": ["/tmp/a", 7]}), encoding="utf-8")
    with pytest.raises(ValueError, match="work_roots"):
        load_config(path)


# --- work-roots registry ---


def test_work_roots_empty_means_no_access(project_server) -> None:
    base, _tmp_path = project_server
    payload = get_json(base, "/api/work-roots")
    assert payload == {"ok": True, "roots": []}


def test_work_roots_lists_registered_entries(project_server) -> None:
    base, tmp_path = project_server
    project = _make_project(tmp_path)
    _set_roots(tmp_path, [str(project)])
    payload = get_json(base, "/api/work-roots")
    assert payload["ok"] is True
    (entry,) = payload["roots"]
    assert entry == {
        "id": root_id(project),
        "path": str(project.resolve()),
        "display_name": "client-a",
    }
    again = get_json(base, "/api/work-roots")
    assert again["roots"] == payload["roots"]


def test_work_roots_validates_at_request_time(project_server) -> None:
    base, tmp_path = project_server
    project = _make_project(tmp_path)
    _set_roots(tmp_path, [str(project)])
    assert get_json(base, "/api/work-roots")["ok"] is True
    (project / "src" / "main.py").unlink()
    (project / "src").rmdir()
    project.rmdir()
    with pytest.raises(HTTPError) as raised:
        get_json(base, "/api/work-roots")
    assert raised.value.code == 500
    raised.value.close()


def test_work_roots_refuses_runtime_overlap(project_server) -> None:
    base, tmp_path = project_server
    (tmp_path / "data").mkdir(exist_ok=True)
    _set_roots(tmp_path, [str(tmp_path / "data")])
    with pytest.raises(HTTPError) as raised:
        get_json(base, "/api/work-roots")
    assert raised.value.code == 500
    raised.value.close()


# --- project-tagged run requests ---


def test_run_request_accepts_project_id_and_path(project_server) -> None:
    base, tmp_path = project_server
    project = _make_project(tmp_path)
    _set_roots(tmp_path, [str(project)])
    session_id = _new_session(base)

    by_id = post_json(
        base,
        f"/api/chat/sessions/{session_id}/run-request",
        {"text": "Fix the bug", "project": root_id(project)},
    )
    assert by_id["ok"] is True
    run = _read_run(tmp_path, by_id["run_id"])
    assert run["project_id"] == str(project.resolve())

    by_path = post_json(
        base,
        f"/api/chat/sessions/{session_id}/run-request",
        {"text": "Fix it again", "project": str(project)},
    )
    assert by_path["ok"] is True
    assert _read_run(tmp_path, by_path["run_id"])["project_id"] == str(project.resolve())


def test_run_request_without_project_stays_unscoped(project_server) -> None:
    base, tmp_path = project_server
    session_id = _new_session(base)
    receipt = post_json(
        base, f"/api/chat/sessions/{session_id}/run-request", {"text": "Status report"}
    )
    assert receipt["ok"] is True
    assert _read_run(tmp_path, receipt["run_id"])["project_id"] is None


def test_run_request_unknown_project_is_400_without_side_effects(project_server) -> None:
    base, tmp_path = project_server
    project = _make_project(tmp_path)
    _set_roots(tmp_path, [str(project)])
    session_id = _new_session(base)
    with pytest.raises(HTTPError) as raised:
        post_json(
            base,
            f"/api/chat/sessions/{session_id}/run-request",
            {"text": "Fix the bug", "project": "no-such-root"},
        )
    assert raised.value.code == 400
    raised.value.close()
    assert not (tmp_path / "data" / "runs").exists()
    assert not (tmp_path / "data" / "inbox").exists()


def test_run_request_project_with_empty_roots_is_400(project_server) -> None:
    base, _tmp_path = project_server
    session_id = _new_session(base)
    with pytest.raises(HTTPError) as raised:
        post_json(
            base,
            f"/api/chat/sessions/{session_id}/run-request",
            {"text": "Fix the bug", "project": "anything"},
        )
    assert raised.value.code == 400
    raised.value.close()


# --- staged review + approve/apply ---


def _staged_run(tmp_path: Path, project: Path, run_id: str = "r1") -> dict:
    record = {
        "id": run_id,
        "title": "Staged fix",
        "status": "queued",
        "project_id": str(project.resolve()),
        "staged": [stage_file(project, "src/main.py", "new\n")],
    }
    _write_run(tmp_path, run_id, record)
    return record


def test_staged_review_renders_diffs(project_server) -> None:
    base, tmp_path = project_server
    project = _make_project(tmp_path)
    _set_roots(tmp_path, [str(project)])
    _staged_run(tmp_path, project)
    payload = get_json(base, "/api/runs/r1/staged")
    assert payload["ok"] is True
    (view,) = payload["files"]
    assert view["relpath"] == "src/main.py"
    assert view["digest"] == digest("new\n")
    assert "-old" in view["diff"] and "+new" in view["diff"]


def test_staged_review_empty_for_unstaged_run(project_server) -> None:
    base, tmp_path = project_server
    _write_run(tmp_path, "r1", {"id": "r1", "title": "Plain", "status": "queued"})
    payload = get_json(base, "/api/runs/r1/staged")
    assert payload == {"ok": True, "files": []}


def test_staged_review_unknown_run_is_404(project_server) -> None:
    base, _tmp_path = project_server
    with pytest.raises(HTTPError) as raised:
        get_json(base, "/api/runs/nope/staged")
    assert raised.value.code == 404
    raised.value.close()


def test_approve_staged_applies_and_marks_run(project_server) -> None:
    base, tmp_path = project_server
    project = _make_project(tmp_path)
    _set_roots(tmp_path, [str(project)])
    _staged_run(tmp_path, project)
    payload = post_json(base, "/api/runs/r1/approve-staged", {"approved": True})
    assert payload["ok"] is True
    assert payload["applied"] == [{"relpath": "src/main.py", "digest": digest("new\n")}]
    assert (project / "src" / "main.py").read_text(encoding="utf-8") == "new\n"
    run = _read_run(tmp_path, "r1")
    assert run["staged_approved"] is True
    assert run["staged_applied"] is True
    assert run["staged_checks"] == "none"


def test_approve_staged_conflict_applies_nothing(project_server) -> None:
    base, tmp_path = project_server
    project = _make_project(tmp_path)
    _set_roots(tmp_path, [str(project)])
    _staged_run(tmp_path, project)
    (project / "src" / "main.py").write_text("someone else\n", encoding="utf-8")
    with pytest.raises(HTTPError) as raised:
        post_json(base, "/api/runs/r1/approve-staged", {"approved": True})
    assert raised.value.code == 409
    raised.value.close()
    assert (project / "src" / "main.py").read_text(encoding="utf-8") == "someone else\n"
    run = _read_run(tmp_path, "r1")
    assert run.get("staged_applied") is not True


def test_approve_staged_tampered_record_is_409(project_server) -> None:
    base, tmp_path = project_server
    project = _make_project(tmp_path)
    _set_roots(tmp_path, [str(project)])
    record = _staged_run(tmp_path, project)
    record["staged"][0]["content"] = "evil\n"
    _write_run(tmp_path, "r1", record)
    with pytest.raises(HTTPError) as raised:
        post_json(base, "/api/runs/r1/approve-staged", {"approved": True})
    assert raised.value.code == 409
    raised.value.close()
    assert (project / "src" / "main.py").read_text(encoding="utf-8") == "old\n"


def test_reject_staged_marks_run_without_applying(project_server) -> None:
    base, tmp_path = project_server
    project = _make_project(tmp_path)
    _set_roots(tmp_path, [str(project)])
    _staged_run(tmp_path, project)
    payload = post_json(base, "/api/runs/r1/approve-staged", {"approved": False})
    assert payload == {"ok": True, "id": "r1", "applied": []}
    assert (project / "src" / "main.py").read_text(encoding="utf-8") == "old\n"
    run = _read_run(tmp_path, "r1")
    assert run["staged_approved"] is False
    assert run["staged_applied"] is False


def test_approve_staged_validates_request(project_server) -> None:
    base, tmp_path = project_server
    with pytest.raises(HTTPError) as raised:
        post_json(base, "/api/runs/nope/approve-staged", {"approved": True})
    assert raised.value.code == 404
    raised.value.close()

    _write_run(tmp_path, "plain", {"id": "plain", "status": "queued"})
    with pytest.raises(HTTPError) as raised:
        post_json(base, "/api/runs/plain/approve-staged", {"approved": True})
    assert raised.value.code == 400
    raised.value.close()

    project = _make_project(tmp_path)
    _set_roots(tmp_path, [str(project)])
    _staged_run(tmp_path, project, run_id="r2")
    with pytest.raises(HTTPError) as raised:
        post_json(base, "/api/runs/r2/approve-staged", {"approved": "yes"})
    assert raised.value.code == 400
    raised.value.close()


def test_approve_staged_unknown_project_is_400(project_server) -> None:
    base, tmp_path = project_server
    project = _make_project(tmp_path)
    _set_roots(tmp_path, [str(project)])
    record = _staged_run(tmp_path, project)
    record["project_id"] = str((tmp_path / "elsewhere").resolve())
    _write_run(tmp_path, "r1", record)
    with pytest.raises(HTTPError) as raised:
        post_json(base, "/api/runs/r1/approve-staged", {"approved": True})
    assert raised.value.code == 400
    raised.value.close()
    assert (project / "src" / "main.py").read_text(encoding="utf-8") == "old\n"

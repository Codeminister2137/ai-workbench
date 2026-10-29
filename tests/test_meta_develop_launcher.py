"""Offline checks for the bounded Meta CLI launcher, never inference."""

import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "meta_develop", Path(__file__).parents[1] / "scripts/meta-develop.py"
)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
URL = "https://api.meta.ai/v1/responses"


@pytest.mark.parametrize(
    "extra",
    [
        {"model": "other"},
        {"stream": True},
        {"previous_response_id": "old"},
        {"input": "x" * 131073},
        {"max_output_tokens": -1},
        {"tools": [{"type": "web_search"}]},
        {"input": [{"type": "input_image"}]},
    ],
)
def test_unsafe_or_unbounded_payload_refused(extra):
    with pytest.raises(ValueError):
        launcher.admit({"model": "muse-spark-1.3", **extra}, URL, "POST")


def test_output_cap_and_nonpersistent_mode_preserve_context():
    context = [{"role": "user", "content": "Keep complete instructions"}]
    body = json.loads(
        launcher.admit(
            {
                "model": "muse-spark-1.3",
                "input": context,
                "store": True,
                "max_output_tokens": 99999,
            },
            URL,
            "POST",
        )
    )
    assert body["input"] == context
    assert body["store"] is False
    assert body["max_output_tokens"] == 8192
    assert launcher.RESERVE * launcher.MAX_CALLS <= 2


def test_other_destination_refused():
    with pytest.raises(ValueError):
        launcher.admit({"model": "muse-spark-1.3"}, "https://example.com", "POST")


def test_shared_allowance_stops_before_ninth_send_and_after_expiry():
    receipt = {"requests": []}
    for _ in range(8):
        launcher.reserve(receipt, 1, 100)
    with pytest.raises(ValueError):
        launcher.reserve(receipt, 2, 100)
    assert len(receipt["requests"]) == 8
    with pytest.raises(ValueError):
        launcher.reserve({"requests": []}, 900, 100)


def test_catalog_contains_only_selected_meta_route():
    import tomllib

    catalog = launcher.meta_catalog(
        Path(__file__).parents[1] / "packages/ai_orchestrator/examples/model_catalog.toml"
    )
    assert [model["route_id"] for model in tomllib.loads(catalog)["models"]] == [
        "meta/muse-spark-1.3"
    ]


def test_chat_reuses_existing_cli_history_and_one_shared_transport_budget(tmp_path, monkeypatch):
    """Real coding-chat controller, synthetic replies; never network or physical approvals."""
    import contextlib

    from ai_agent import coding_chat_cli
    from ai_provider.chat_transcripts import SQLiteChatTranscriptStore

    root = tmp_path / "public"
    root.mkdir()
    (root / ".git").mkdir()
    (root / "AGENTS.md").write_text("Synthetic public fixture. Do not edit files.")
    database = tmp_path / "existing.sqlite3"
    database.touch()
    SQLiteChatTranscriptStore(database)
    bodies = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size):
            return json.dumps(
                {
                    "id": "synthetic",
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "Synthetic reply"}],
                        }
                    ],
                    "usage": {"input_tokens": 10, "output_tokens": 2},
                }
            ).encode()

    class Opener:
        def open(self, request, *, timeout):
            bodies.append(json.loads(request.data))
            return Response()

    def conversation(controller, execute, **kwargs):
        for index in range(8):
            assert controller.turn(f"Synthetic owner turn {index}", execute).returncode == 0
        controller.turn("Ninth synthetic turn must not reach network", execute)
        pytest.fail("Expected the shared allowance to stop the conversation")

    monkeypatch.setenv("META_API_KEY", "synthetic-no-real-key")
    monkeypatch.setattr(launcher, "build_opener", lambda *args: Opener())
    monkeypatch.setattr(coding_chat_cli, "run_terminal_conversation", conversation)
    monkeypatch.setattr(
        coding_chat_cli.CodingChatInput, "in_flight", lambda self: contextlib.nullcontext()
    )
    run = tmp_path / "run"
    monkeypatch.setattr(
        "sys.argv",
        [
            "meta-develop",
            "--chat",
            "--repo-root",
            str(root),
            "--session-db",
            str(database),
            "--run-dir",
            str(run),
        ],
    )
    assert launcher.main() == 2
    assert len(bodies) == 8
    assert "Synthetic owner turn 0" in json.dumps(bodies[1])
    assert "Synthetic reply" in json.dumps(bodies[1])
    assert len(json.loads((run / "receipt.json").read_text())["requests"]) == 8


def test_chat_refuses_missing_database_before_creating_any_run_storage(tmp_path, monkeypatch):
    root = tmp_path / "public"
    root.mkdir()
    (root / ".git").mkdir()
    (root / "AGENTS.md").write_text("Synthetic instructions")
    run = tmp_path / "run"
    monkeypatch.setattr(
        "sys.argv",
        [
            "meta-develop",
            "--chat",
            "--repo-root",
            str(root),
            "--session-db",
            str(tmp_path / "absent.sqlite3"),
            "--run-dir",
            str(run),
        ],
    )
    with pytest.raises(SystemExit, match="2"):
        launcher.main()
    assert not run.exists()


@pytest.mark.parametrize("raises", [False, True])
def test_hands_off_grants_file_edits_denies_execution_and_restores_policy(raises):
    from ai_agent.contracts import PermissionAction
    from ai_agent.permissions import PermissionPolicy

    original = PermissionPolicy.__dict__["from_approval_preset"]
    try:
        with launcher.hands_off_file_policy(True):
            policy = PermissionPolicy.from_approval_preset("workspace_write")
            assert (
                policy.read_action
                == policy.search_action
                == policy.write_action
                == PermissionAction.ALLOW
            )
            assert policy.shell_action == policy.custom_action == PermissionAction.DENY
            assert (
                PermissionPolicy.from_approval_preset("read_only").write_action
                == PermissionAction.DENY
            )
            if raises:
                raise RuntimeError("synthetic scope failure")
    except RuntimeError:
        assert raises
    assert PermissionPolicy.__dict__["from_approval_preset"] is original
    assert (
        PermissionPolicy.from_approval_preset("workspace_write").shell_action
        == PermissionAction.ASK_USER
    )

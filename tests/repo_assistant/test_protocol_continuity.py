"""Fresh scripted HTTP fallback through the real two-turn foreground CLI.

No real accounts or inference: both origins are loopback, replies are scripted,
and trusted_local is a fixture policy for one fixed bounded sleeping child.
This tests runtime composition, not real-model quality or full C6 acceptance.
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ai_agent import repo_coding_assistant as cli
from ai_agent.processes import ProcessTool
from ai_provider.adapters import openai_compatible, openai_responses
from ai_provider.adapters.baseten import BASETEN_HACKATHON_MODEL
from ai_provider.chat_transcripts import SQLiteChatTranscriptStore
from ai_provider.foreground_tools import ACTIVE_FOREGROUND


def test_two_turn_chat_preserves_process_and_history_across_protocol_fallback(
    tmp_path, monkeypatch, request
):
    instructions = "Synthetic continuity: preserve protected.txt and add no dependencies."
    first = "Start one bounded child and retain its owned handle across the next turn."
    second = "Observe that same child, then stop it without creating another process."
    first_report = "Scripted first report: child observed running after protocol fallback."
    (tmp_path / "AGENTS.md").write_text(instructions, encoding="utf-8")
    protected = tmp_path / "protected.txt"
    protected.write_bytes(b"protected fixture bytes\n")
    argv = [sys.executable, "-I", "-c", "import time; time.sleep(45)"]
    observations, requests, errors = [], [], []
    supervisors = []
    original_execute = ProcessTool.execute

    def observed_execute(tool, arguments, context):
        if tool.operation == "start":
            assert arguments == {"argv": argv}
            assert not observations
            supervisors.append(tool.supervisor)
        result = original_execute(tool, arguments, context)
        observations.append((tool.operation, dict(result.metadata)))
        return result

    monkeypatch.setattr(ProcessTool, "execute", observed_execute)
    request.addfinalizer(lambda: [supervisor.close() for supervisor in supervisors])
    # Resolve only synthetic route credentials; fixture never loads the ignored .env.
    monkeypatch.setenv("META_API_KEY", "synthetic-meta-loopback-only")
    monkeypatch.setenv("BASETEN_API_KEY", "synthetic-baseten-loopback-only")
    monkeypatch.setattr(cli, "read_execution_allowance", lambda *_args, **_kwargs: None)
    meta_calls = 0
    baseten_calls = 0

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            nonlocal meta_calls, baseten_calls
            try:
                size = int(self.headers["Content-Length"])
                assert 0 < size <= 200000
                body = json.loads(self.rfile.read(size))
                requests.append((self.path, body))
                assert len(requests) <= 8
                status = 200
                if self.path == "/v1/responses":
                    assert self.headers["Authorization"] == "Bearer synthetic-meta-loopback-only"
                    assert body["model"] == "muse-spark-1.3" and body["store"] is False
                    meta_calls += 1
                    if meta_calls == 1:
                        reply = {
                            "status": "completed",
                            "output": [
                                {
                                    "type": "function_call",
                                    "id": "item-start",
                                    "call_id": "call-start",
                                    "name": "process_start",
                                    "arguments": json.dumps({"argv": argv}),
                                }
                            ],
                        }
                    else:
                        status, reply = 429, {"error": {"message": "Scripted capacity limit"}}
                else:
                    assert self.path == "/v1/chat/completions"
                    assert self.headers["Authorization"] == "Bearer synthetic-baseten-loopback-only"
                    assert body["model"] == BASETEN_HACKATHON_MODEL
                    assert observations and observations[0][0] == "start"
                    baseten_calls += 1
                    wire = json.dumps(body)
                    assert instructions in wire and first in wire
                    handle = observations[0][1]["process_handle"]
                    if baseten_calls >= 3:
                        assert second in wire and first_report in wire
                    if baseten_calls in {1, 3, 4}:
                        operation = "process_stop" if baseten_calls == 4 else "process_status"
                        message = {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": f"call-{baseten_calls}",
                                    "type": "function",
                                    "function": {
                                        "name": operation,
                                        "arguments": json.dumps({"process_handle": handle}),
                                    },
                                }
                            ],
                        }
                    else:
                        assert baseten_calls in {2, 5}
                        message = {
                            "role": "assistant",
                            "content": first_report
                            if baseten_calls == 2
                            else "Scripted second report: owned child stopped.",
                        }
                    reply = {"choices": [{"message": message, "finish_reason": "stop"}]}
                encoded = json.dumps(reply).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
            except Exception as error:
                errors.append(repr(error))
                self.send_error(400)

        def log_message(self, format: str, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def stop_server():
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()

    request.addfinalizer(stop_server)
    base = f"http://127.0.0.1:{server.server_port}/v1"
    for module, endpoint in (
        (openai_responses, "/responses"),
        (openai_compatible, "/chat/completions"),
    ):
        original = module.urlopen

        def guarded_open(http_request, *, timeout, expected=base + endpoint, opener=original):
            assert http_request.full_url == expected and 0 < timeout <= 2
            return opener(http_request, timeout=timeout)

        monkeypatch.setattr(module, "urlopen", guarded_open)
    catalog = tmp_path / "catalog.toml"
    catalog.write_text(
        "\n".join(
            f'''[[models]]
route_id = "{provider}-loopback"
provider = "{provider}"
model = "{model}"
location = "external"
access_method = "provider_api"
auth_method = "api_key"
billing_source = "{provider}_api_billing"
cost_policy_tier = "prepaid_credits_allowed"
quality = "standard"
latency = "background"
base_url = "{base}"
timeout_seconds = 2
[models.capabilities]
chat = true
tools = true
'''
            for provider, model in (
                ("meta", "muse-spark-1.3"),
                ("baseten", BASETEN_HACKATHON_MODEL),
            )
        ),
        encoding="utf-8",
    )
    answers = iter([second, "/exit"])

    def automated_input(_prompt):
        answer = next(answers)
        if answer == second:
            foreground = ACTIVE_FOREGROUND.get()
            assert foreground is not None and foreground.supervisor is supervisors[0]
            assert (
                foreground.supervisor.status(observations[0][1]["process_handle"])["status"]
                == "running"
            )
        return answer

    monkeypatch.setattr("builtins.input", automated_input)
    assert (
        cli.main(
            [
                "--mode",
                "coding-chat",
                "--execute",
                "--repo-root",
                str(tmp_path),
                "--catalog",
                str(catalog),
                "--route-id",
                "meta-loopback",
                "--privacy",
                "external_allowed",
                "--cost-policy",
                "prepaid_credits_allowed",
                "--skip-prompt-review",
                "--approval-policy",
                "trusted_local",
                "--timeout-seconds",
                "2",
                "--turn-timeout-seconds",
                "15",
                "--away-minutes",
                "0.5",
                "--max-action-rounds",
                "5",
                first,
            ]
        )
        == 0
    )
    assert not errors
    assert (meta_calls, baseten_calls) == (3, 5)
    assert [operation for operation, _ in observations] == ["start", "status", "status", "stop"]
    assert all(item["pid"] == observations[0][1]["pid"] for _, item in observations)
    assert all(item["status"] == "running" for _, item in observations[:-1])
    assert observations[-1][1]["status"] != "running"
    assert supervisors[0].closed
    assert protected.read_bytes() == b"protected fixture bytes\n"
    store = SQLiteChatTranscriptStore(tmp_path / "data/repo-assistant-chats.sqlite3")
    session = store.latest_session(repo_root=tmp_path)
    assert session is not None
    messages = store.list_messages(session.session_id)
    assert [message.role for message in messages] == ["user", "assistant", "user", "assistant"]
    assert messages[0].content == first and messages[2].content == second
    assert first_report in messages[1].content
    for message in (messages[1], messages[3]):
        assert message.metadata is not None
        assert message.metadata["effective_route_id"] == "baseten-loopback"
        assert message.metadata["returncode"] == 0

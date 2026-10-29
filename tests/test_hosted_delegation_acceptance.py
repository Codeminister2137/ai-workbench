"""Fresh scripted loopback composition, not hosted inference/model-quality evidence."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from ai_agent import AgentLoop, PermissionManager, PermissionPolicy, mcp_server
from ai_agent.delegation_scope import DelegationBudget, DelegationScope
from ai_agent.processes import ProcessSupervisor, ProcessTool
from ai_agent.tools import EditFileTool, ToolContext, ToolRegistry
from ai_agent.tools.delegation import DelegateTaskTool
from ai_agent.tools.shell import RunCommandTool
from ai_orchestrator import CostPolicyTier, TaskProfile
from ai_orchestrator import PrivacyClass as RoutingPrivacy
from ai_provider import BackendConfig, PrivacyClass, ProviderError, ProviderKind, create_chat_client
from ai_provider.adapters import openai_compatible, openai_responses
from ai_provider.adapters.baseten import BASETEN_HACKATHON_MODEL

INSTRUCTIONS = "Synthetic acceptance: preserve protected checks and report observed effects."
OBJECTIVE = "Implement the synthetic action digest and validate it within inherited authority."
REFERENCE = (
    "import hashlib, json\n"
    "def action_digest(action):\n"
    "    return hashlib.sha256(json.dumps(action, sort_keys=True, "
    "separators=(',', ':')).encode()).hexdigest()\n"
)
CHECK = """import hashlib, json, os, runpy
assert 'META_API_KEY' not in os.environ
assert 'ACCEPTANCE_PRIVATE_TOKEN' not in os.environ
digest = runpy.run_path('candidate.py')['action_digest']
for action in ({'tool': 'edit', 'size': 3}, {'size': 3, 'tool': 'edit'}, {}, {'nested': [1, 2]}):
    encoded = json.dumps(action, sort_keys=True, separators=(',', ':')).encode()
    expected = hashlib.sha256(encoded).hexdigest()
    assert digest(action) == expected
assert digest({'size': 3}) != digest({'size': 4})
print('five independent digest cases passed; credentials absent')
"""


def response(*calls, text="Scripted report; inspect host evidence before acceptance."):
    output = (
        [
            {
                "type": "function_call",
                "id": f"item-{name}",
                "call_id": f"call-{name}",
                "name": name,
                "arguments": json.dumps(arguments),
            }
            for name, arguments in calls
        ]
        if calls
        else [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        ]
    )
    return {
        "status": "completed",
        "output": output,
        "usage": {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7},
    }


@pytest.mark.parametrize("provider", ["meta", "baseten"])
@pytest.mark.parametrize("mode", ["complete", "read_only", "outside_scope", "budget_exhausted"])
def test_nested_delegation_over_real_transport(tmp_path, monkeypatch, provider, mode, request):
    """Use scripted replies with actual HTTP, tools, commands and owned processes."""
    candidate = tmp_path / "candidate.py"
    candidate.write_text("def action_digest(action):\n    return 'seeded-defect'\n")
    protected = tmp_path / "protected_check.py"
    protected.write_text(CHECK)
    protected_hash = hashlib.sha256(protected.read_bytes()).hexdigest()
    monkeypatch.setenv("META_API_KEY", "synthetic-owner-credential-not-for-workers")
    monkeypatch.setenv("ACCEPTANCE_PRIVATE_TOKEN", "synthetic-private-token-not-for-workers")
    quoted_python = "'" + sys.executable.replace("'", "''") + "'"
    command = ("& " if sys.platform == "win32" else "") + quoted_python + " -I protected_check.py"
    worker_env = ToolContext(tmp_path, inherit_environment=False).command_environment()
    baseline = subprocess.run(
        [sys.executable, "-I", str(protected)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=worker_env,
        timeout=5,
    )
    assert baseline.returncode != 0
    assert "digest(action) == expected" in baseline.stderr

    requests = []
    replies = []
    server_errors = []
    model = "muse-spark-1.3" if provider == "meta" else BASETEN_HACKATHON_MODEL
    endpoint = "/responses" if provider == "meta" else "/chat/completions"

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            try:
                assert self.path == "/v1" + endpoint
                assert self.headers.get("Authorization") == "Bearer synthetic-loopback-only"
                size = int(self.headers["Content-Length"])
                assert 0 < size <= 131072
                body = json.loads(self.rfile.read(size))
                assert body["model"] == model
                if provider == "meta":
                    assert body["store"] is False
                assert len(requests) < len(replies)
                requests.append(body)
                reply = replies[len(requests) - 1]
                if provider == "baseten":
                    calls = [item for item in reply["output"] if item["type"] == "function_call"]
                    message = {"role": "assistant", "content": None}
                    if calls:
                        message["tool_calls"] = [
                            {
                                "id": item["call_id"],
                                "type": "function",
                                "function": {
                                    "name": item["name"],
                                    "arguments": item["arguments"],
                                },
                            }
                            for item in calls
                        ]
                    else:
                        message["content"] = reply["output"][0]["content"][0]["text"]
                    reply = {
                        "choices": [
                            {"message": message, "finish_reason": "tool_calls" if calls else "stop"}
                        ],
                        "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
                    }
                encoded = json.dumps(reply).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
            except Exception as error:
                server_errors.append(type(error).__name__)
                self.send_error(400)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def close_server():
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    request.addfinalizer(close_server)
    base_url = f"http://127.0.0.1:{server.server_port}/v1"
    client = create_chat_client(
        BackendConfig(
            provider=ProviderKind(provider),
            model=model,
            base_url=base_url,
            api_key="synthetic-loopback-only",
            timeout_seconds=1,
        )
    )
    # No unregistered origin or fresh child client can silently escape this fixture.
    transport = openai_responses if provider == "meta" else openai_compatible
    original_open = transport.urlopen

    def loopback_only(request, *, timeout):
        assert request.full_url == base_url + endpoint
        assert timeout <= 1
        return original_open(request, timeout=timeout)

    monkeypatch.setattr(transport, "urlopen", loopback_only)
    other_transport = openai_compatible if provider == "meta" else openai_responses
    monkeypatch.setattr(
        other_transport,
        "urlopen",
        lambda *_args, **_kwargs: pytest.fail("Unexpected alternate protocol transport"),
    )
    monkeypatch.setattr(
        mcp_server,
        "create_chat_client",
        lambda *_: pytest.fail("Child replaced the already-approved executor"),
    )
    catalog = tmp_path / "catalog.toml"
    catalog.write_text(f'''[[models]]
route_id = "scripted-{provider}-loopback"
provider = "{provider}"
product = "{provider}"
model = "{model}"
location = "external"
access_method = "provider_api"
auth_method = "api_key"
billing_source = "{provider}_api_billing"
cost_policy_tier = "prepaid_credits_allowed"
quality = "standard"
latency = "background"
base_url = "{base_url}"
timeout_seconds = 5
[models.capabilities]
chat = true
tools = true
''')
    deadline = time.perf_counter() + 40
    budget = DelegationBudget(
        8 if mode in {"read_only", "budget_exhausted"} else 9, deadline, tools_remaining=12
    )
    supervisor = ProcessSupervisor(tmp_path)
    request.addfinalizer(supervisor.close)
    handle = supervisor.start([sys.executable, "-I", "-c", "import time; time.sleep(60)"], env={})
    initial = supervisor.status(handle)
    assert initial["status"] == "running"
    child_tools = ["delegate_task", "edit_file", "run_command"]
    replies.extend(
        [
            response(
                (
                    "delegate_task",
                    {
                        "task": (
                            "Delegate implementation and validation; preserve the protected check."
                        ),
                        "permission_profile": "read_only" if mode == "read_only" else "inherit",
                        "allowed_tools": child_tools,
                        "allowed_paths": ["candidate.py"],
                        "allowed_commands": [command],
                    },
                )
            ),
            response(
                (
                    "delegate_task",
                    {
                        "task": "Implement and validate candidate.py.",
                        "permission_profile": "trusted_local",
                    },
                )
            ),
            response(
                (
                    "edit_file",
                    {
                        "path": "protected_check.py" if mode == "outside_scope" else "candidate.py",
                        "new_text": REFERENCE,
                    },
                )
            ),
            response(("run_command", {"command": command, "timeout_seconds": 5})),
            response(),
            response(),
            response(("process_status", {"process_handle": handle})),
            response(("process_stop", {"process_handle": handle})),
            response(),
        ]
    )
    if mode == "read_only":
        # The read-only child cannot delegate (CUSTOM), so no grandchild starts.
        # Its own edit/check attempts are refused; then the parent resumes.
        replies.pop(5)
    profile = TaskProfile(
        privacy_class=RoutingPrivacy.EXTERNAL_ALLOWED,
        cost_policy_tier=CostPolicyTier.PREPAID_CREDITS_ALLOWED,
    )
    runner = mcp_server._local_read_only_delegated_task_runner(
        catalog_path=catalog,
        timeout_seconds=5,
        max_iterations=6,
        parent_profile=profile,
        deadline=deadline,
    )
    registry = ToolRegistry(
        (
            EditFileTool(),
            RunCommandTool(),
            DelegateTaskTool(runner),
            ProcessTool(supervisor, "status"),
            ProcessTool(supervisor, "stop"),
        )
    )
    manager = PermissionManager(PermissionPolicy.permissive())
    scope = DelegationScope(
        registry,
        manager,
        tmp_path,
        budget,
        instructions=INSTRUCTIONS,
        objective=OBJECTIVE,
        backends=frozenset({(provider, model, base_url)}),
        approved_client=client,
        request_timeout_seconds=1,
    )
    loop = AgentLoop(
        client,
        registry,
        ToolContext(tmp_path, delegation=scope),
        permissions=manager,
        max_iterations=9,
        deadline=deadline,
    )
    try:
        if mode == "budget_exhausted":
            with pytest.raises(ProviderError, match="allowance.*exhausted"):
                loop.run(
                    OBJECTIVE,
                    system_prompt=INSTRUCTIONS,
                    privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
                )
            assert len(requests) == 8
        else:
            result = loop.run(
                OBJECTIVE, system_prompt=INSTRUCTIONS, privacy_class=PrivacyClass.EXTERNAL_ALLOWED
            )
            assert len(requests) == (8 if mode == "read_only" else 9)
            assert result.tool_results[0].is_error is (mode in {"read_only", "outside_scope"})
            assert result.tool_results[1].metadata["status"] == "running"
            assert result.tool_results[1].metadata["pid"] == initial["pid"]
            assert result.tool_results[2].metadata["status"] != "running"
        assert budget.replies_remaining == 0
        assert hashlib.sha256(protected.read_bytes()).hexdigest() == protected_hash
        assert (candidate.read_text() == REFERENCE) is (mode not in {"read_only", "outside_scope"})
        checked = subprocess.run(
            [sys.executable, "-I", str(protected)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            env=worker_env,
            timeout=5,
        )
        assert (checked.returncode == 0) is (mode not in {"read_only", "outside_scope"})
        wire = json.dumps(requests)
        assert "synthetic-owner-credential-not-for-workers" not in wire
        assert "synthetic-private-token-not-for-workers" not in wire
        assert INSTRUCTIONS in json.dumps(requests[1])
        assert OBJECTIVE in json.dumps(requests[1])
        assert INSTRUCTIONS in json.dumps(requests[2])
        assert not server_errors
    finally:
        supervisor.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()
    assert supervisor.status(handle)["status"] != "running"
    with pytest.raises(ValueError, match="closed"):
        supervisor.start([sys.executable, "-c", "pass"])
    with pytest.raises(ValueError, match="Unknown"):
        ProcessSupervisor(tmp_path).status(handle)

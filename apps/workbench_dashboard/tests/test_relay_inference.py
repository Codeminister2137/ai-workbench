"""Synthetic P2 proof: Mai tool turns and full host fallback over the R mailbox."""

import json
import os
import threading
import time
import uuid
from dataclasses import replace
from pathlib import Path

import pytest
from ai_agent.loop import AgentLoop
from ai_agent.permissions import PermissionManager, PermissionPolicy
from ai_agent.relay_client import RelayChatClient, decode_request, request_payload
from ai_agent.tools.base import ToolContext, ToolRegistry
from ai_agent.tools.filesystem import CreateFileTool
from ai_orchestrator import (
    AccessMethod,
    AccessRoute,
    AuthMethod,
    BackendLocation,
    BillingSource,
    CostPolicyTier,
    ModelBackend,
    ModelCapabilities,
    ModelCatalogEntry,
    PrivacyClass,
    QualityThreshold,
    TaskCapability,
    TaskProfile,
    prepare_execution,
)
from ai_provider.contracts import (
    AIMessage,
    AIRequest,
    AIResponse,
    AIToolCall,
    BackendInfo,
    MessageRole,
    ProviderContinuation,
)
from ai_provider.contracts import (
    BackendLocation as ProviderLocation,
)
from ai_provider.contracts import (
    PrivacyClass as ProviderPrivacy,
)
from ai_provider.errors import ProviderError, ProviderErrorCategory
from relay_inference import HostRelayInference, build_mai_relay
from relay_mailbox import HostMediator, RelayError, RelayGrant, WorkerClient

PRIVACY = ProviderPrivacy.PUBLIC_OR_LOW_RISK
GRANT = RelayGrant("p2-synthetic", "host-policy")


def _parts():
    catalog = tuple(
        ModelCatalogEntry(
            backend=ModelBackend(
                route=AccessRoute(
                    route_id=f"route-{index}",
                    provider="synthetic",
                    product="synthetic",
                    model=f"model-{index}",
                    location=BackendLocation.EXTERNAL,
                    access_method=AccessMethod.PROVIDER_API,
                    auth_method=AuthMethod.NONE,
                    billing_source=billing,
                    cost_policy_tier=CostPolicyTier.BILLING_ALLOWED,
                ),
                capabilities=ModelCapabilities(chat=True, tools=True),
            ),
            quality=QualityThreshold.HIGH,
        )
        for index, billing in enumerate(
            (
                BillingSource.OPENAI_API_BILLING,
                BillingSource.REQUESTY_BILLING,
                BillingSource.GOOGLE_API_BILLING,
                BillingSource.META_API_BILLING,
            )
        )
    )
    profile = TaskProfile(
        privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
        cost_policy_tier=CostPolicyTier.BILLING_ALLOWED,
        required_capabilities=frozenset({TaskCapability.CHAT, TaskCapability.TOOLS}),
        user_route_id_override="route-0",
    )
    plan = prepare_execution(
        "Synthetic relay", profile, catalog, review_prompt=False
    ).execution_plan
    assert plan is not None
    return profile, catalog, plan.target


def make_host(execute, *, excluded=frozenset(), deadline=None):
    profile, catalog, initial = _parts()
    return HostRelayInference(
        profile,
        catalog,
        initial,
        execute,
        privacy=PRIVACY,
        excluded_route_ids=excluded,
        deadline=deadline,
        priority=tuple(f"route-{i}" for i in range(4)),
    )


def response(text="synthetic-ok", *, calls=()):
    return AIResponse(
        AIMessage(MessageRole.ASSISTANT, text, tool_calls=calls),
        BackendInfo("synthetic", "model-3", ProviderLocation.EXTERNAL),
        tool_calls=calls,
    )


def serve(tmp_path, host, turns, action):
    mediator = HostMediator(
        tmp_path, GRANT, lambda *_: pytest.fail("legacy bypass"), complete_request=host
    )
    errors = []

    def run():
        try:
            for _ in range(turns):
                assert mediator.serve_once(timeout_s=5)
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    try:
        return action(RelayChatClient(WorkerClient(tmp_path, GRANT), timeout_s=5))
    finally:
        thread.join(timeout=6)
        assert not thread.is_alive()
        assert not errors


def test_synthetic_mai_tool_turn_walks_entire_tree_then_reuses_route(tmp_path):
    """Real AgentLoop, file exchange and orchestrator; only inference is synthetic."""
    attempts = []
    observed = []

    def scoped(target, request):
        attempts.append(target.route_id)
        observed.append(request)
        if target.route_id != "route-3":
            raise ProviderError("synthetic exhausted", category=ProviderErrorCategory.USAGE_LIMIT)
        if not any(message.role == MessageRole.TOOL for message in request.messages):
            return response(
                "",
                calls=(
                    AIToolCall(
                        "call-1",
                        "create_file",
                        {
                            "path": "proof.txt",
                            "content": "worker-tool-effect",
                        },
                    ),
                ),
            )
        assert request.messages[-1].tool_call_id == "call-1"
        assert "Error:" not in request.messages[-1].content
        return response()

    host = make_host(scoped)
    result = serve(
        tmp_path,
        host,
        2,
        lambda client: AgentLoop(
            client,
            ToolRegistry((CreateFileTool(),)),
            ToolContext(tmp_path),
            max_iterations=3,
            permissions=PermissionManager(PermissionPolicy.workspace_write()),
        ).run("Synthetic P2 proof", privacy_class=PRIVACY),
    )
    assert result.response.message.content == "synthetic-ok"
    assert result.iterations == 2
    assert attempts == ["route-0", "route-1", "route-2", "route-3", "route-3"]
    assert all(request.messages == observed[0].messages for request in observed[:4])
    assert [item["route_id"] for item in host.executor.attempts[:3]] == attempts[:3]
    assert (tmp_path / "proof.txt").read_text() == "worker-tool-effect"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["proof.txt"]


@pytest.mark.skipif(
    os.environ.get("RUN_P2_DOCKER_PROOF") != "1", reason="explicit bounded native synthetic proof"
)
def test_native_container_mai_fallback_proof(tmp_path):
    """Network-none container, real Mai/tools, synthetic host inference, four routes.

    Inject the new client source into the existing image for this proof only;
    no image rebuild, extra boundary mount or production enablement is implied.
    """
    import ai_agent.relay_client as relay_module
    from docker_compose import RelaySpec, build_relay_project, compose, compose_file_content

    mailbox = tmp_path / "mailbox"
    mailbox.mkdir()
    source = Path(relay_module.__file__).read_text(encoding="utf-8")
    program = (
        "import sys, json, types, pathlib, socket\n"
        "sys.path.insert(0, '/boundary')\n"
        "from relay_mailbox import WorkerClient, RelayGrant\n"
        "module = types.ModuleType('ai_agent.relay_client')\n"
        "sys.modules[module.__name__] = module\n"
        f"exec({source!r}, module.__dict__)\n"
        "from ai_agent.loop import AgentLoop\n"
        "from ai_agent.tools.base import ToolContext, ToolRegistry\n"
        "from ai_agent.tools.filesystem import CreateFileTool\n"
        "from ai_agent.permissions import PermissionManager, PermissionPolicy\n"
        "from ai_provider.contracts import PrivacyClass\n"
        "workspace = pathlib.Path('/tmp/p2-workspace'); workspace.mkdir()\n"
        f"transport = WorkerClient('/mailbox', RelayGrant({GRANT.run_id!r}, {GRANT.model!r}))\n"
        "result = AgentLoop(module.RelayChatClient(transport, timeout_s=20),\n"
        "    ToolRegistry((CreateFileTool(),)), ToolContext(workspace), max_iterations=3,\n"
        "    permissions=PermissionManager(PermissionPolicy.workspace_write())).run(\n"
        "    'Synthetic P2 container proof', privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK)\n"
        "assert result.response.message.content == 'synthetic-ok'\n"
        "assert (workspace / 'proof.txt').read_text() == 'worker-tool-effect'\n"
        "assert result.iterations == 2\n"
        "assert not any(row.split()[1] == '00000000' for row in\n"
        "               pathlib.Path('/proc/net/route').read_text().splitlines()[1:])\n"
        "for address in [('1.1.1.1', 443), ('host.docker.internal', 80)]:\n"
        "    try:\n"
        "        connection = socket.create_connection(address, timeout=1)\n"
        "    except OSError:\n"
        "        pass\n"
        "    else:\n"
        "        connection.close(); raise AssertionError('unexpected network access')\n"
        "assert sorted(p.name for p in pathlib.Path('/boundary').iterdir()) == ['relay_mailbox.py']\n"
        "assert not list(pathlib.Path('/mailbox').iterdir())\n"
        "print(json.dumps({'passed': True, 'iterations': result.iterations, 'tool_effect': True,\n"
        "                  'no_default_route': True, 'minimal_boundary': True,\n"
        "                  'public_host_connections_refused': True}))\n"
    )
    spec = RelaySpec(
        run_id=GRANT.run_id,
        project_name="p2-proof-" + uuid.uuid4().hex[:12],
        mailbox_host_path=mailbox,
        relay_module_host_path=Path(__file__).resolve().parents[1] / "relay_mailbox.py",
        worker_command=("python", "-B", "-u", "-c", program),
    )
    config = tmp_path / "compose.yml"
    config.write_text(compose_file_content(spec), encoding="utf-8")
    assert build_relay_project(spec)["services"]["worker"]["network_mode"] == "none"
    attempts = []

    def scoped(target, request):
        attempts.append(target.route_id)
        if target.route_id != "route-3":
            raise ProviderError("synthetic quota", category=ProviderErrorCategory.USAGE_LIMIT)
        if request.messages[-1].role != MessageRole.TOOL:
            return response(
                "",
                calls=(
                    AIToolCall(
                        "call-1",
                        "create_file",
                        {
                            "path": "proof.txt",
                            "content": "worker-tool-effect",
                        },
                    ),
                ),
            )
        assert "Error:" not in request.messages[-1].content
        return response()

    host = make_host(scoped)
    receipt: dict = {"synthetic": True, "passed": False}

    def run(_):
        proc = compose(
            config,
            spec.project_name,
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "worker",
            timeout_seconds=40,
        )
        receipt.update(exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout.splitlines()[-1])["passed"]

    try:
        serve(mailbox, host, 2, run)
        assert attempts == ["route-0", "route-1", "route-2", "route-3", "route-3"]
        receipt["passed"] = True
    finally:
        down = compose(
            config, spec.project_name, "down", "--volumes", "--remove-orphans", timeout_seconds=20
        )
        receipt.update(attempts=attempts, teardown_exit=down.returncode)
        (tmp_path / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        assert down.returncode == 0


@pytest.mark.parametrize(
    "category",
    [
        ProviderErrorCategory.AUTHENTICATION,
        ProviderErrorCategory.PRIVACY_POLICY,
        ProviderErrorCategory.NON_RETRYABLE,
    ],
)
def test_refusals_do_not_fallback_or_leak_secrets(tmp_path, category):
    attempts = []

    def deny(target, request):
        attempts.append(target.route_id)
        raise ProviderError("private-secret", category=category)

    with pytest.raises(RelayError) as error:
        serve(
            tmp_path,
            make_host(deny),
            1,
            lambda client: client.complete(
                AIRequest((AIMessage(MessageRole.USER, "x"),), privacy_class=PRIVACY)
            ),
        )
    assert "private-secret" not in str(error.value)
    assert attempts == ["route-0"]


def test_exclusion_and_exhaustion_are_not_single_model_fallback():
    attempts = []

    def fail(target, request):
        attempts.append(target.route_id)
        raise ProviderError("limit", category=ProviderErrorCategory.USAGE_LIMIT)

    host = make_host(fail, excluded=frozenset({"route-1"}))
    payload = request_payload(AIRequest((AIMessage(MessageRole.USER, "x"),), privacy_class=PRIVACY))
    with pytest.raises(ProviderError):
        host(payload)
    assert attempts == ["route-0", "route-2", "route-3"]
    with pytest.raises(ProviderError):
        host(payload)
    assert attempts == ["route-0", "route-2", "route-3"]


def test_expired_deadline_prevents_admission():
    host = make_host(lambda *_: pytest.fail("expired admission"))
    host.executor.deadline = time.perf_counter() - 1
    with pytest.raises(ProviderError, match="deadline"):
        host(request_payload(AIRequest((AIMessage(MessageRole.USER, "x"),), privacy_class=PRIVACY)))


def test_overloaded_routes_walk_full_tree_without_exhausting_billing():
    attempts = []

    def scoped(target, request):
        attempts.append(target.route_id)
        if target.route_id != "route-3":
            raise ProviderError("server_overloaded", category=ProviderErrorCategory.RETRYABLE)
        return response()

    host = make_host(scoped)
    payload = request_payload(AIRequest((AIMessage(MessageRole.USER, "x"),), privacy_class=PRIVACY))
    assert host(payload)["message"]["content"] == "synthetic-ok"
    assert attempts == ["route-0", "route-1", "route-2", "route-3"]
    assert host.executor.overloaded == {"route-0", "route-1", "route-2"}
    assert not host.executor.exhausted


@pytest.mark.parametrize("parameters", [None, "invalid", [None], ["invalid"]])
def test_malformed_tool_parameters_refused_before_admission(parameters):
    payload = request_payload(AIRequest((AIMessage(MessageRole.USER, "x"),), privacy_class=PRIVACY))
    payload["tools"] = [{"name": "tool", "description": "test", "parameters": parameters}]
    host = make_host(lambda *_: pytest.fail("invalid admission"))
    with pytest.raises(ValueError, match="invalid relay tool parameter"):
        host(payload)


@pytest.mark.parametrize(
    "mutation",
    [
        {"model": "worker-selected"},
        {"metadata": {"endpoint": "http://host"}},
        {"privacy_class": "local_only"},
        {"messages": []},
        {"temperature": float("nan")},
    ],
)
def test_worker_cannot_change_host_scope(mutation):
    data = request_payload(AIRequest((AIMessage(MessageRole.USER, "x"),), privacy_class=PRIVACY))
    with pytest.raises(ValueError):
        decode_request({**data, **mutation}, privacy=PRIVACY)


def test_foreign_run_refused_before_scoped_callback(tmp_path):
    (tmp_path / "request.json").write_text(
        json.dumps(
            {
                "id": "foreign",
                "run_id": "other",
                "model": GRANT.model,
                "request": {},
            }
        )
    )
    mediator = HostMediator(
        tmp_path,
        GRANT,
        lambda *_: pytest.fail("legacy"),
        complete_request=lambda _: pytest.fail("foreign admission"),
    )
    assert mediator.serve_once(timeout_s=1)
    assert "error" in json.loads((tmp_path / "response.json").read_text())


def test_mai_factory_refuses_legacy_bypass(tmp_path):
    profile, catalog, initial = _parts()
    mediator = build_mai_relay(
        str(tmp_path),
        GRANT,
        profile,
        catalog,
        initial,
        lambda *_: pytest.fail("legacy bypass"),
        privacy=PRIVACY,
    )
    (tmp_path / "request.json").write_text(
        json.dumps(
            {
                "id": "legacy",
                "model": GRANT.model,
                "messages": [{"role": "user", "content": "x"}],
            }
        )
    )
    assert mediator.serve_once(timeout_s=1)
    assert "error" in json.loads((tmp_path / "response.json").read_text())


def test_continuation_stays_host_side_and_is_removed_on_route_switch():
    requests = []
    continuation = ProviderContinuation(
        "synthetic", "model-0", "private-endpoint", {"opaque": "private-state"}
    )

    def scoped(target, request):
        requests.append(request)
        if len(requests) == 1:
            return replace(
                response(),
                message=AIMessage(MessageRole.ASSISTANT, "first", continuation=continuation),
            )
        if len(requests) == 2:
            assert request.messages[1].continuation == continuation
            raise ProviderError("limit", category=ProviderErrorCategory.USAGE_LIMIT)
        assert all(message.continuation is None for message in request.messages)
        return response()

    host = make_host(scoped)
    first = host(
        request_payload(AIRequest((AIMessage(MessageRole.USER, "x"),), privacy_class=PRIVACY))
    )
    assert "private" not in json.dumps(first)
    host(
        request_payload(
            AIRequest(
                (
                    AIMessage(MessageRole.USER, "x"),
                    AIMessage(MessageRole.ASSISTANT, "first"),
                    AIMessage(MessageRole.USER, "next"),
                ),
                privacy_class=PRIVACY,
            )
        )
    )


def test_all_prior_continuations_survive_three_turns_and_rewrites_invalidate_them():
    requests = []
    continuation = ProviderContinuation("synthetic", "model-0", "private", {"opaque": "state"})

    def scoped(target, request):
        requests.append(request)
        return replace(
            response(),
            message=AIMessage(
                MessageRole.ASSISTANT,
                f"answer-{len(requests)}",
                continuation=continuation,
            ),
        )

    host = make_host(scoped)
    messages = [AIMessage(MessageRole.USER, "first")]
    for index in range(3):
        host(request_payload(AIRequest(tuple(messages), privacy_class=PRIVACY)))
        messages.extend(
            (
                AIMessage(MessageRole.ASSISTANT, f"answer-{index + 1}"),
                AIMessage(MessageRole.USER, "next"),
            )
        )
    assert requests[2].messages[1].continuation == continuation
    assert requests[2].messages[3].continuation == continuation
    messages[0] = AIMessage(MessageRole.USER, "rewritten")
    host(request_payload(AIRequest(tuple(messages), privacy_class=PRIVACY)))
    assert all(message.continuation is None for message in requests[-1].messages)

"""OpenRouter free admission, protocol and routing tests; no network or inference."""

import json
from pathlib import Path

import pytest
from ai_orchestrator import BillingSource, CostPolicyTier, load_model_catalog
from ai_provider import (
    AIMessage,
    AIRequest,
    AIStreamFinal,
    AIToolCall,
    BackendConfig,
    MessageRole,
    PrivacyClass,
    ProviderError,
    ProviderKind,
    create_chat_client,
)
from ai_provider.adapters.openrouter import OpenRouterFreeChatClient
from ai_provider.coding_assist import backend_config_from_execution_target
from ai_provider.errors import ProviderErrorCategory

MODEL = "qwen/qwen3.8-27b:free"


@pytest.mark.parametrize("structured", [False, True])
def test_continuation_roundtrip_is_transient_and_origin_bound(monkeypatch, tmp_path, structured):
    from dataclasses import replace

    from ai_provider import ProviderContinuation, SQLiteChatTranscriptStore
    from ai_provider.adapters.openai_compatible import OpenAICompatibleChatClient
    from ai_provider.chat_transcripts import messages_to_ai_messages
    from ai_provider.native_admission import NativeCodingClient

    secret = "synthetic-private-continuation"
    state = (
        {
            "reasoning_details": [
                {
                    "type": "reasoning.encrypted",
                    "data": secret,
                    "id": "r1",
                    "format": "test",
                    "index": 0,
                }
            ]
        }
        if structured
        else {"reasoning": secret}
    )
    raw = {"choices": [{"message": {"content": "answer", **state}, "finish_reason": "stop"}]}
    calls = transport(monkeypatch, response=raw)
    adapter = client()
    assert isinstance(adapter, OpenRouterFreeChatClient)
    answer = adapter.complete(request())
    assert answer.message.continuation is not None
    assert answer.message.continuation.payload == state
    followup = AIRequest(
        (answer.message,),
        privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
        temperature=1.0,
        max_output_tokens=123,
    )
    adapter.complete(followup)
    sent = json.loads(calls[-1].data)
    assert sent["messages"][0] == {"role": "assistant", "content": "answer", **state}
    assert sent["temperature"] == 1.0 and sent["max_tokens"] == 123
    assert "reasoning" not in sent  # No unrequested generation setting.
    assert secret not in repr(answer)
    for changed in (
        {"provider": "requesty"},
        {"model": "other:free"},
        {"base_url": "https://elsewhere.invalid/v1"},
    ):
        foreign = replace(
            answer.message, continuation=replace(answer.message.continuation, **changed)
        )
        assert adapter._message_payload(foreign, MODEL) == {
            "role": "assistant",
            "content": "answer",
        }
    for role in (MessageRole.USER, MessageRole.TOOL, MessageRole.SYSTEM):
        assert secret not in repr(
            adapter._message_payload(replace(answer.message, role=role), MODEL)
        )
    other = OpenAICompatibleChatClient(BackendConfig(ProviderKind.REQUESTY, MODEL))
    assert secret not in repr(other._message_payload(answer.message, MODEL))

    oversized = replace(
        answer.message,
        continuation=ProviderContinuation(
            "openrouter", MODEL, adapter.base_url, {"reasoning": secret * 1000}
        ),
    )
    diagnostics = []
    admitted = NativeCodingClient(adapter, adapter.config, 2048, diagnostics.append)
    before = len(calls)
    with pytest.raises(ProviderError, match="does not fit"):
        admitted.complete(AIRequest((oversized,), privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK))
    assert len(calls) == before and secret not in repr(diagnostics)
    store = SQLiteChatTranscriptStore(tmp_path / "chat.sqlite3")
    session = store.create_session(
        repo_root=tmp_path, title="test", privacy_class="public_or_low_risk"
    )
    store.append_message(
        session.session_id, role=answer.message.role, content=answer.message.content
    )
    assert messages_to_ai_messages(store.list_messages(session.session_id))[0].continuation is None
    assert secret.encode() not in store.path.read_bytes()


def test_stream_continuation_preserves_order_fragments_and_hides_metadata(monkeypatch):
    chunks = [
        {
            "choices": [
                {
                    "delta": {
                        "reasoning_details": [
                            {"type": "reasoning.text", "index": 0, "text": "private-"}
                        ]
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "delta": {
                        "content": "ok",
                        "reasoning_details": [
                            {"index": 0, "text": "state"},
                            {"type": "reasoning.encrypted", "index": 1, "data": "opaque"},
                        ],
                    }
                }
            ]
        },
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
    ]
    transport(monkeypatch, response=chunks)
    adapter = client()
    assert isinstance(adapter, OpenRouterFreeChatClient)
    events = list(adapter.stream(request()))
    final = events[-1]
    assert isinstance(final, AIStreamFinal)
    answer = final.response
    assert answer.message.continuation is not None
    assert answer.message.continuation.payload == {
        "reasoning_details": [
            {"type": "reasoning.text", "index": 0, "text": "private-state"},
            {"type": "reasoning.encrypted", "index": 1, "data": "opaque"},
        ]
    }
    assert "private-" not in repr(events) and "opaque" not in repr(events)
    assert (
        adapter._message_payload(answer.message, MODEL)["reasoning_details"]
        == (answer.message.continuation.payload["reasoning_details"])
    )


def test_real_tool_loop_replays_continuation_and_tool_ids(monkeypatch, tmp_path):
    from ai_agent import AgentLoop, ToolContext, default_coding_tools

    (tmp_path / "public.txt").write_text("public fixture", encoding="utf-8")
    replies = iter(
        [
            {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "reasoning": "private-loop-state",
                            "tool_calls": [
                                {
                                    "id": "call1",
                                    "type": "function",
                                    "function": {
                                        "name": "read_file",
                                        "arguments": '{"path": "public.txt"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
            {"choices": [{"message": {"content": "reviewed"}, "finish_reason": "stop"}]},
        ]
    )
    calls = transport(monkeypatch, response=lambda: next(replies))
    result = AgentLoop(client(), default_coding_tools(), ToolContext(tmp_path)).run(
        "Read public.txt", privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK
    )
    assert result.response.message.content == "reviewed"
    assert not result.tool_results[0].is_error
    posts = [json.loads(call.data) for call in calls if call.get_method() == "POST"]
    assistant, observation = posts[1]["messages"][-2:]
    assert assistant["reasoning"] == "private-loop-state"
    assert assistant["tool_calls"][0]["id"] == observation["tool_call_id"] == "call1"
    assert "public fixture" in observation["content"]
    assert "private-loop-state" not in repr(result)


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        return json.dumps(self.payload).encode()

    def __iter__(self):
        return iter([f"data: {json.dumps(row)}\n".encode() for row in self.payload])


def row(**changes):
    return {
        "id": MODEL,
        "pricing": {"prompt": "0", "completion": "0"},
        "supported_parameters": ["tools", "max_tokens", "temperature"],
        **changes,
    }


def request(**changes):
    return AIRequest(
        messages=(AIMessage(MessageRole.USER, "Synthetic input"),),
        privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
        **changes,
    )


def client(**changes):
    return create_chat_client(
        BackendConfig(provider=ProviderKind.OPENROUTER, model=MODEL, api_key="test-only", **changes)
    )


def transport(monkeypatch, *, rows=None, quota=None, response=None):
    calls = []

    def send(http_request, **kwargs):
        calls.append(http_request)
        if http_request.full_url.endswith("/models"):
            return Response({"data": [row()] if rows is None else rows})
        if http_request.full_url.endswith("/key"):
            return Response(
                {
                    "data": {
                        "is_free_tier": False,
                        "free_model_daily_requests": {"used": 0, "limit": 50, "remaining": 50}
                        if quota is None
                        else quota,
                    }
                }
            )
        return Response(
            (response() if callable(response) else response)
            if response is not None
            else {
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 2,
                    "total_tokens": 14,
                    "cost": 0,
                },
            }
        )

    monkeypatch.setattr("ai_provider.adapters.openrouter.urlopen", send)
    monkeypatch.setattr("ai_provider.adapters.openai_compatible.urlopen", send)
    return calls


@pytest.mark.parametrize(
    "pricing",
    [
        {},
        {"prompt": "0"},
        {"prompt": "0", "completion": "0.1"},
        {"prompt": False, "completion": 0},
        {"prompt": "NaN", "completion": 0},
        {"prompt": 0, "completion": 0, "input_cache_read": "0.01"},
        {"prompt": 0, "completion": 0, "request": None},
        {"prompt": 0, "completion": 0, "overrides": [{"completion": 1}]},
    ],
)
@pytest.mark.parametrize("stream", [False, True])
def test_unknown_or_nonzero_prices_refuse_before_post(monkeypatch, pricing, stream):
    calls = transport(monkeypatch, rows=[row(pricing=pricing)])
    with pytest.raises(ProviderError, match="not verified free"):
        list(client().stream(request())) if stream else client().complete(request())
    assert [call.get_method() for call in calls] == ["GET"]


@pytest.mark.parametrize(
    "quota",
    [
        {},
        {"used": 2, "limit": 50, "remaining": 50},
        {"used": 0, "limit": 50, "remaining": True},
        {"used": 51, "limit": 50, "remaining": -1},
        {"used": 50, "limit": 50, "remaining": 0},
    ],
)
def test_quota_refuses_without_post(monkeypatch, quota):
    calls = transport(monkeypatch, quota=quota)
    with pytest.raises(ProviderError):
        client().complete(request())
    assert [call.get_method() for call in calls] == ["GET", "GET"]


@pytest.mark.parametrize("model", ["openrouter/free", "openrouter/auto", "qwen/paid"])
def test_model_override_cannot_bypass_guard(monkeypatch, model):
    calls = transport(monkeypatch)
    with pytest.raises(ProviderError, match="exact named"):
        client().complete(request(model=model))
    assert calls == []


@pytest.mark.parametrize("rows", [[], [row(), row()], [row(supported_parameters=[])]])
def test_exact_unique_tool_capable_model_required(monkeypatch, rows):
    calls = transport(monkeypatch, rows=rows)
    with pytest.raises(ProviderError):
        client().complete(request())
    assert len(calls) == 1


@pytest.mark.parametrize("require_free_model", [False, True])
def test_guard_is_mandatory_and_rechecked_each_turn(monkeypatch, require_free_model):
    calls = transport(monkeypatch)
    chat = client(require_free_model=require_free_model)
    assert isinstance(chat, OpenRouterFreeChatClient)
    for _ in range(2):
        response = chat.complete(request())
        assert response.backend.provider == "openrouter"
        assert response.usage.total_tokens == 14
    assert [call.get_method() for call in calls] == ["GET", "GET", "POST"] * 2
    payload = json.loads(calls[2].data)
    assert payload["provider"] == {
        "require_parameters": True,
        "data_collection": "deny",
        "max_price": {"prompt": 0, "completion": 0, "request": 0, "image": 0},
    }
    assert not {"models", "route", "plugins"} & payload.keys()


def test_preserves_instructions_history_and_tool_result(monkeypatch):
    calls = transport(monkeypatch)
    messages = (
        AIMessage(MessageRole.SYSTEM, "Required instructions"),
        AIMessage(MessageRole.USER, "Original request"),
        AIMessage(
            MessageRole.ASSISTANT, "", tool_calls=(AIToolCall("c1", "read_file", {"path": "a.py"}),)
        ),
        AIMessage(MessageRole.TOOL, "Complete file content", tool_call_id="c1"),
    )
    client().complete(AIRequest(messages=messages, privacy_class=PrivacyClass.EXTERNAL_ALLOWED))
    payload = json.loads(calls[-1].data)
    assert [m["content"] for m in payload["messages"]] == [m.content for m in messages]
    assert payload["messages"][2]["tool_calls"][0]["id"] == "c1"
    assert payload["messages"][3]["tool_call_id"] == "c1"


def test_local_only_refuses_before_metadata_or_inference(monkeypatch):
    calls = transport(monkeypatch)
    with pytest.raises(ProviderError):
        client().complete(AIRequest(messages=request().messages))
    assert calls == []


def test_custom_endpoint_cannot_receive_credentials():
    with pytest.raises(ProviderError, match="official API"):
        client(base_url="https://example.invalid/v1")


def test_stream_usage_receipt_and_tool_fragments(monkeypatch):
    chunks = [
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "c1",
                                "function": {"name": "read_file", "arguments": '{"path":'},
                            }
                        ]
                    },
                    "finish_reason": None,
                }
            ]
        },
        {
            "choices": [
                {
                    "delta": {"tool_calls": [{"index": 0, "function": {"arguments": '"a.py"}'}}]},
                    "finish_reason": "tool_calls",
                }
            ]
        },
        {
            "choices": [{"delta": {}, "finish_reason": "tool_calls"}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14, "cost": 0},
        },
    ]
    transport(monkeypatch, response=chunks)
    event = list(client().stream(request()))[-1]
    assert isinstance(event, AIStreamFinal)
    final = event.response
    assert final.tool_calls == (AIToolCall("c1", "read_file", {"path": "a.py"}),)
    assert final.usage.total_tokens == 14
    assert final.raw_metadata["stream_usage_chunk"]["usage"]["cost"] == 0


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(
    "code,category",
    [
        (402, ProviderErrorCategory.USAGE_LIMIT),
        (429, ProviderErrorCategory.RATE_LIMIT),
        (503, ProviderErrorCategory.RETRYABLE),
    ],
)
def test_embedded_errors_normalized_without_remote_text(monkeypatch, stream, code, category):
    error = {"error": {"code": code, "message": "secret input echo"}}
    transport(monkeypatch, response=[error] if stream else error)
    with pytest.raises(ProviderError) as result:
        list(client().stream(request())) if stream else client().complete(request())
    assert result.value.category == category
    assert "secret" not in str(result.value)


def test_opt_in_catalog_provenance_and_existing_fallback():
    root = Path(__file__).resolve().parents[1]
    catalog = load_model_catalog(
        root / "packages/ai_orchestrator/examples/openrouter_free_catalog.toml"
    )
    route = catalog[0].backend
    assert route.provider == "openrouter" and route.billing_source is BillingSource.OPENROUTER_FREE
    assert route.cost_policy_tier is CostPolicyTier.FREE_ONLY
    default = load_model_catalog(root / "packages/ai_orchestrator/examples/model_catalog.toml")
    assert catalog[1] == next(
        item for item in default if item.backend.route_id == catalog[1].backend.route_id
    )


def test_conventional_environment_key(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER_KIND", "openrouter")
    monkeypatch.setenv("AI_PROVIDER_MODEL", MODEL)
    monkeypatch.delenv("AI_PROVIDER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    assert BackendConfig.from_env().api_key == "test-key"


def test_generic_transport_cannot_bypass_guards():
    from ai_provider.adapters.openai_compatible import OpenAICompatibleChatClient

    with pytest.raises(ProviderError, match="guarded free client"):
        OpenAICompatibleChatClient(
            BackendConfig(provider=ProviderKind.OPENROUTER, model=MODEL, api_key="test-only")
        )


@pytest.mark.parametrize("is_free_tier", [True, None, "false"])
def test_free_or_unknown_plan_privacy_entitlement_refuses(monkeypatch, is_free_tier):
    calls = transport(monkeypatch)

    def key_metadata(http_request, **kwargs):
        calls.append(http_request)
        return Response(
            {
                "data": {
                    "is_free_tier": is_free_tier,
                    "free_model_daily_requests": {"used": 0, "limit": 50, "remaining": 50},
                }
            }
        )

    monkeypatch.setattr("ai_provider.adapters.openrouter.urlopen", key_metadata)
    chat = client()
    assert isinstance(chat, OpenRouterFreeChatClient)
    with pytest.raises(ProviderError, match="privacy-filter entitlement"):
        chat._verify_free_quota()
    assert [call.get_method() for call in calls] == ["GET"]


@pytest.mark.parametrize("exhaust_after_tool", [False, True])
def test_shared_tool_loop_preserves_effects_and_rechecks_quota(
    monkeypatch, tmp_path, exhaust_after_tool
):
    from ai_agent import (
        AgentLoop,
        PermissionManager,
        PermissionPolicy,
        ToolContext,
        default_coding_tools,
    )

    original = tmp_path / "test_original.py"
    original.write_text("def test_original():\n    assert True\n", encoding="utf-8")
    quota = {"used": 0, "limit": 50, "remaining": 50}
    replies = iter(
        [
            {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "c1",
                                    "function": {
                                        "name": "create_file",
                                        "arguments": json.dumps(
                                            {"path": "result.txt", "content": "synthetic result"}
                                        ),
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
            {"choices": [{"message": {"content": "Finished"}, "finish_reason": "stop"}]},
        ]
    )

    def next_reply():
        if exhaust_after_tool:
            quota.update(used=50, remaining=0)
        return next(replies)

    calls = transport(monkeypatch, quota=quota, response=next_reply)
    loop = AgentLoop(
        client(),
        default_coding_tools(),
        ToolContext(tmp_path),
        permissions=PermissionManager(policy=PermissionPolicy.permissive()),
        max_iterations=2,
    )
    if exhaust_after_tool:
        with pytest.raises(ProviderError) as result:
            loop.run(
                "Create result.txt",
                system_prompt="Preserve original tests",
                privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
            )
        assert result.value.category is ProviderErrorCategory.USAGE_LIMIT
        assert result.value.partial_messages[-1].role is MessageRole.TOOL
        assert [call.get_method() for call in calls] == ["GET", "GET", "POST", "GET", "GET"]
    else:
        result = loop.run(
            "Create result.txt",
            system_prompt="Preserve original tests",
            privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
        )
        assert result.response.message.content == "Finished"
        assert len(result.tool_results) == 1
        assert [call.get_method() for call in calls] == ["GET", "GET", "POST"] * 2
        payload = json.loads(calls[-1].data)
        assert payload["messages"][0]["content"] == "Preserve original tests"
        assert payload["messages"][-1]["role"] == "tool"
        assert payload["tools"]
    assert (tmp_path / "result.txt").read_text() == "synthetic result"
    assert original.read_text() == "def test_original():\n    assert True\n"


def test_same_tier_fallback_obeys_quality_privacy_and_exhaustion():
    from dataclasses import replace

    from ai_orchestrator import PrivacyClass, QualityThreshold, TaskCapability, TaskProfile
    from ai_orchestrator.fallback import fallback_candidates
    from ai_orchestrator.planner import ExecutionTarget

    root = Path(__file__).resolve().parents[1]
    catalog = load_model_catalog(
        root / "packages/ai_orchestrator/examples/openrouter_free_catalog.toml"
    )
    backend = catalog[0].backend
    target = ExecutionTarget(
        backend.route_id,
        backend.provider,
        backend.product,
        backend.model,
        backend.access_method,
        backend.auth_method,
        backend.billing_source,
        backend.cost_policy_tier,
    )
    config = backend_config_from_execution_target(target)
    assert config.provider is ProviderKind.OPENROUTER and config.require_free_model
    profile = TaskProfile(
        privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
        quality_threshold=QualityThreshold.STANDARD,
        cost_policy_tier=CostPolicyTier.FREE_ONLY,
        required_capabilities=frozenset({TaskCapability.CHAT, TaskCapability.TOOLS}),
    )
    assert fallback_candidates(profile, catalog, target) == (catalog[1],)
    assert not fallback_candidates(
        replace(profile, quality_threshold=QualityThreshold.HIGH), catalog, target
    )
    assert not fallback_candidates(
        replace(profile, privacy_class=PrivacyClass.LOCAL_ONLY), catalog, target
    )
    assert not fallback_candidates(
        profile, catalog, target, exhausted_billing_sources=frozenset({"requesty_billing"})
    )

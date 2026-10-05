"""Offline research execution and provenance boundary tests."""

import hashlib
import io
import json
import os
import socket
from argparse import ArgumentParser, Namespace
from datetime import UTC, datetime
from email.message import Message
from pathlib import Path
from types import SimpleNamespace

import pytest
from ai_agent.contracts import ToolCall
from ai_agent.permissions import PermissionManager, PermissionPolicy
from ai_agent.research_evidence import ResearchSources
from ai_agent.tools import research_http
from ai_agent.tools.base import ToolContext
from ai_agent.tools.research import FetchURLTool, ResearchReportTool
from ai_orchestrator.tool_profiles import select_tool_profile
from ai_provider.orchestrated_runs import OrchestratedStagePlanItem, SQLiteOrchestratedRunStore
from ai_provider.research_execution import ResearchExecution, validate_research_arguments
from test_research_report_validation import report


def receipt():
    return {
        "requested_url": "https://docs.python.org/3/",
        "final_url": "https://docs.python.org/3/",
        "http_status": 200,
        "fetched_at_utc": datetime.now(UTC).isoformat(),
        "sha256": "a" * 64,
        "bytes_retained": 10,
        "truncated": False,
    }


class TestReportContinuation:
    def test_long_unicode_report_can_be_read_completely_without_losing_the_source_map(
        self, tmp_path
    ):
        content = "Zażółć 🧠\n" * 3_000 + "\nSource map tail: keep this evidence."
        target = tmp_path / "report.md"
        target.write_text(content, encoding="utf-8")
        tool = ResearchReportTool(target, lambda *args: None, write=False)
        recovered = []
        offset = 0
        pages = []
        while True:
            result = tool.run(
                ToolCall("read_research_report", {"offset": offset}), ToolContext(tmp_path)
            )
            assert not result.is_error
            pages.append(result)
            recovered.append(result.output[: result.metadata["returned_chars"]])
            offset = result.metadata["next_offset"]
            if offset is None:
                break
            assert f"offset={offset}" in result.output
        assert "".join(recovered) == content
        assert "Source map tail" in pages[-1].output and "End of report" in pages[-1].output
        assert len({result.metadata["sha256"] for result in pages}) == 1
        assert all(result.metadata["total_chars"] == len(content) for result in pages)
        assert target.read_text(encoding="utf-8") == content

    def test_small_report_read_without_arguments_preserves_original_output(self, tmp_path):
        target = tmp_path / "report.md"
        target.write_text("complete report", encoding="utf-8")
        result = ResearchReportTool(target, lambda *args: None, write=False).run(
            ToolCall("read_research_report", {}), ToolContext(tmp_path)
        )
        assert result.output == "complete report"
        assert result.metadata["next_offset"] is None

    @pytest.mark.parametrize("offset", [-1, True, "0", 1_000_001, 100])
    def test_invalid_or_out_of_range_offset_does_not_read_another_file(self, tmp_path, offset):
        target = tmp_path / "report.md"
        target.write_text("small", encoding="utf-8")
        result = ResearchReportTool(target, lambda *args: None, write=False).run(
            ToolCall("read_research_report", {"offset": offset}), ToolContext(tmp_path)
        )
        assert result.is_error and "offset" in result.output

    def test_externally_oversized_report_is_refused_instead_of_silently_cut_off(self, tmp_path):
        target = tmp_path / "report.md"
        target.write_bytes(b"x" * 1_000_001)
        result = ResearchReportTool(target, lambda *args: None, write=False).run(
            ToolCall("read_research_report", {}), ToolContext(tmp_path)
        )
        assert result.is_error and "1 MB" in result.output


def valid_report():
    return report(
        source=f"S1 https://docs.python.org/3/ accessed {datetime.now(UTC).date()}; fetched"
    )


@pytest.fixture
def execution(tmp_path):
    store = SQLiteOrchestratedRunStore(tmp_path / "runs.sqlite3")
    run = store.create_run(
        repo_root=tmp_path,
        mode="implement",
        prompt="research",
        budget_seconds=300,
        approval_policy="trusted_local",
        primary_route_id=None,
        primary_provider="ollama",
        primary_model="test",
    )
    store.replace_stage_plan(
        run.run_id, [OrchestratedStagePlanItem("implementation", "primary", "research")]
    )
    store.start_stage(run.run_id, "implementation")
    return ResearchExecution(tmp_path, Path("report.md"), store, run.run_id)


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.1.2.3",
        "169.254.169.254",
        "192.168.1.1",
        "::1",
        "fc00::1",
        "fe80::1",
        "224.0.0.1",
        "::ffff:127.0.0.1",
    ],
)
def test_fetch_rejects_nonpublic_dns(monkeypatch, ip):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(0, 0, 0, "", (ip, 80))])
    with pytest.raises(ValueError, match="non-public"):
        research_http.public_endpoint("https://example.com/")


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://user:password@example.com/",
        "http://example.com:8080/",
        "https://example.com/\nheader",
        "http://example.com\\private/",
    ],
)
def test_fetch_rejects_unsafe_urls(url):
    with pytest.raises(ValueError):
        research_http.public_endpoint(url)


def fake_http(monkeypatch, responses):
    requests = []
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(0, 0, 0, "", ("93.184.216.34", 443))]
    )

    class Connection:
        sock = None

        def __init__(self, host, port, ip, timeout):
            self.response = responses.pop(0)
            requests.append((host, port, ip, timeout))

        def request(self, method, target, headers):
            requests.append((method, target, headers))

        def getresponse(self):
            return self.response

        def close(self):
            requests.append("closed")

    monkeypatch.setattr(research_http, "_PinnedHTTPS", Connection)
    monkeypatch.setattr(research_http, "_PinnedHTTP", Connection)
    return requests


def response(body=b"source", *, status=200, mime="text/plain", **headers):
    message = Message()
    message["Content-Type"] = mime
    for key, value in headers.items():
        message[key.replace("_", "-")] = value
    stream = io.BytesIO(body)
    return SimpleNamespace(
        status=status, headers=message, getheader=message.get, read1=stream.read1
    )


def test_fetch_bounds_bytes_and_records_real_digest(monkeypatch):
    requests = fake_http(monkeypatch, [response(b"x" * (research_http.MAX_SOURCE_BYTES + 100))])
    source = research_http.fetch_public_url("https://example.com/path?q=1")
    assert len(source.body) == research_http.MAX_SOURCE_BYTES
    assert source.receipt["sha256"] == hashlib.sha256(source.body).hexdigest()
    assert source.receipt["truncated"] is True
    assert requests[1][0:2] == ("GET", "/path?q=1")
    assert set(requests[1][2]) == {"User-Agent", "Accept", "Accept-Encoding"}
    assert requests[-1] == "closed"


def test_redirect_is_revalidated_before_connection(monkeypatch):
    requests = fake_http(monkeypatch, [response(status=302, Location="http://localhost/")])
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, *a, **k: [
            (0, 0, 0, "", ("127.0.0.1" if host == "localhost" else "93.184.216.34", 80))
        ],
    )
    with pytest.raises(ValueError, match="non-public"):
        research_http.fetch_public_url("https://example.com/")
    assert requests[-1] == "closed"
    assert len(requests) == 3


@pytest.mark.parametrize(
    "reply",
    [response(status=404), response(mime="application/pdf"), response(Content_Encoding="gzip")],
)
def test_unsupported_fetch_has_no_receipt(monkeypatch, reply):
    fake_http(monkeypatch, [reply])
    with pytest.raises(ValueError):
        research_http.fetch_public_url("https://example.com/")


def test_tool_extracts_text_links_and_records_fetch(tmp_path):
    events = []
    source = research_http.FetchedSource(
        b'<p>Evidence</p><script>evil()</script><a href="/next">Next</a>',
        "text/html",
        "utf-8",
        receipt(),
    )
    tool = FetchURLTool(
        lambda kind, value: events.append((kind, value)), fetcher=lambda url: source
    )
    result = tool.execute({"url": "https://docs.python.org/3/"}, ToolContext(tmp_path))
    assert "Evidence" in result.output and "evil()" not in result.output
    assert "https://docs.python.org/next" in result.output
    assert events == [("fetch_receipts", source.receipt)]


def test_source_limit_resolves_aliases_and_rejects_before_body(monkeypatch, tmp_path):
    first = response(b"first evidence")
    repeated = response(b"updated evidence")
    blocked = response(b"must not be read")
    reads = []
    original_read = blocked.read1
    blocked.read1 = lambda size: reads.append(size) or original_read(size)
    fake_http(
        monkeypatch,
        [first, response(status=302, Location="https://example.com/final"), repeated, blocked],
    )
    events = []
    sources = ResearchSources(1)
    tool = FetchURLTool(lambda kind, value: events.append(value), sources=sources)
    context = ToolContext(tmp_path)
    tool.execute({"url": "https://example.com/final"}, context)
    tool.execute({"url": "https://example.com/alias"}, context)
    with pytest.raises(ValueError, match="maximum.*exhausted"):
        tool.execute({"url": "https://example.com/new"}, context)
    assert not reads
    assert len(events) == 2
    assert sources.successful_urls == {"https://example.com/final"}
    assert sources.excerpts["https://example.com/final"].text == "updated evidence"


def test_failed_fetch_does_not_use_a_source_slot(monkeypatch, tmp_path):
    fake_http(monkeypatch, [response(status=404), response(b"success")])
    sources = ResearchSources(1)
    tool = FetchURLTool(lambda *a: None, sources=sources)
    with pytest.raises(ValueError, match="404"):
        tool.execute({"url": "https://example.com/broken"}, ToolContext(tmp_path))
    assert not sources.successful_urls
    tool.execute({"url": "https://example.com/working"}, ToolContext(tmp_path))
    assert sources.successful_urls == {"https://example.com/working"}


def test_review_excerpts_are_ephemeral_and_missing_after_recomposition(execution, monkeypatch):
    fake_http(monkeypatch, [response(b"distinctive actual source passage")])
    execution.registry.execute(
        ToolCall("fetch_url", {"url": "https://example.com/"}), ToolContext(execution.root)
    )
    assert "distinctive actual source passage" in execution.review_evidence()
    assert "distinctive actual source passage" not in json.dumps(
        execution.store.list_stages(execution.run_id)[0].details
    )
    resumed = ResearchExecution(
        execution.root, Path("report.md"), execution.store, execution.run_id
    )
    assert "distinctive actual source passage" not in resumed.review_evidence()
    receipts = [entry.receipt for entry in execution.sources.excerpts.values()]
    assert resumed.sources.review_payload(receipts)["selected_urls_without_text"] == [
        "https://example.com/"
    ]


def test_source_limit_is_shared_and_restored_from_run_receipts(execution, monkeypatch):
    limited = ResearchExecution(
        execution.root, Path("report.md"), execution.store, execution.run_id, max_sources=1
    )
    fake_http(monkeypatch, [response(b"evidence"), response(b"blocked")])
    limited.registry.execute(
        ToolCall("fetch_url", {"url": "https://example.com/"}), ToolContext(execution.root)
    )
    resumed = ResearchExecution(
        execution.root, Path("report.md"), execution.store, execution.run_id
    )
    result = resumed.registry.execute(
        ToolCall("fetch_url", {"url": "https://example.com/new"}), ToolContext(execution.root)
    )
    assert result.is_error and "exhausted" in result.output
    assert resumed.sources.max_sources == 1
    with pytest.raises(ValueError, match="Cannot change"):
        ResearchExecution(
            execution.root, Path("report.md"), execution.store, execution.run_id, max_sources=2
        )


def test_review_capacity_preserves_report_and_balanced_source_coverage(execution):
    from ai_provider import AIMessage, MessageRole
    from ai_provider.research_execution import bounded_research_messages
    from ai_provider.scrutiny import (
        RESEARCH_SCRUTINY_SYSTEM_PROMPT,
        build_research_scrutiny_prompt,
    )

    execution.target.write_text("Report claim and context. " * 1_000, encoding="utf-8")
    for index in range(30):
        item = {**receipt(), "final_url": f"https://example.com/docs/source-{index}"}
        execution.record("fetch_receipts", item)
        execution.sources.retain(item, "Bounded source text. " * 1_000)
    evidence = execution.review_evidence()
    prompt = build_research_scrutiny_prompt(
        "research " * 100,
        "Assistant claims: " * 200,
        execution_status="completed",
        validation_evidence="Fixture validation passed.",
        research_evidence=evidence,
    )
    messages = (
        AIMessage(MessageRole.SYSTEM, RESEARCH_SCRUTINY_SYSTEM_PROMPT),
        AIMessage(MessageRole.USER, prompt),
    )
    assert bounded_research_messages(messages) == messages
    assert "Report excerpt truncated: True" in evidence
    assert (
        len(
            execution.sources.review_payload(
                [entry.receipt for entry in execution.sources.excerpts.values()]
            )["sources"]
        )
        == 30
    )


@pytest.mark.parametrize(
    "preset,allowed",
    [
        ("read_only", False),
        ("interactive", False),
        ("workspace_write", False),
        ("trusted_local", True),
    ],
)
def test_fetch_uses_existing_custom_permission(preset, allowed):
    tool = FetchURLTool(lambda *a: None)
    permissions = PermissionManager(PermissionPolicy.from_approval_preset(preset))
    assert (
        permissions.check_and_authorize(tool, ToolCall("fetch_url", {"url": "https://example.com"}))
        is allowed
    )


def test_report_tool_only_writes_configured_target(execution):
    context = ToolContext(execution.root)
    result = execution.registry.execute(
        ToolCall("write_research_report", {"content": valid_report(), "path": "source.py"}), context
    )
    assert not result.is_error
    assert execution.target.exists()
    assert not (execution.root / "source.py").exists()
    assert execution.validate() == [
        "claimed fetched source has no successful current-run receipt: https://docs.python.org/3/"
    ]
    execution.record("fetch_receipts", receipt())
    assert execution.validate() == []
    execution.target.write_text(valid_report() + "\nmanual edit", encoding="utf-8")
    assert "report has no matching write receipt from the current run" in execution.validate()


def test_existing_report_without_run_write_is_rejected(execution):
    execution.target.write_text(valid_report(), encoding="utf-8")
    execution.record("fetch_receipts", receipt())
    assert "report has no matching write receipt from the current run" in execution.validate()


def test_parenthetical_citation_feedback_explains_required_syntax(execution):
    execution.record("fetch_receipts", receipt())
    result = execution.registry.execute(
        ToolCall("write_research_report", {"content": valid_report().replace("[S1]", "(S1)")}),
        ToolContext(execution.root),
    )
    assert "literal square brackets, e.g. [S1]" in result.output
    assert execution.validate()


def test_short_report_feedback_is_advisory_but_receipts_remain_required(execution):
    text = valid_report().replace(
        "A synthetic report used for structural tests. " * 170, "Short summary."
    )
    result = execution.registry.execute(
        ToolCall("write_research_report", {"content": text}), ToolContext(execution.root)
    )
    assert "length advisory" in result.output
    assert "Completion checks failed" in result.output
    assert execution.validate() == [
        "claimed fetched source has no successful current-run receipt: https://docs.python.org/3/"
    ]
    execution.record("fetch_receipts", receipt())
    result = execution.registry.execute(
        ToolCall("write_research_report", {"content": text}), ToolContext(execution.root)
    )
    assert "length advisory" in result.output
    assert "Completion checks failed" not in result.output
    assert execution.validate() == []
    execution.target.write_text(text + "manual change", encoding="utf-8")
    assert "report has no matching write receipt from the current run" in execution.validate()


def test_report_write_does_not_modify_hardlink_alias(execution):
    source = execution.root / "source.md"
    source.write_text("preserve", encoding="utf-8")
    os.link(source, execution.target)
    execution.registry.execute(
        ToolCall("write_research_report", {"content": "new report"}), ToolContext(execution.root)
    )
    assert source.read_text() == "preserve"
    assert execution.target.read_text() == "new report"


def test_report_write_rejects_outside_workspace(tmp_path):
    tool = ResearchReportTool(tmp_path.parent / "outside.md", lambda *a: None, write=True)
    result = tool.run(ToolCall(tool.definition.name, {"content": "new"}), ToolContext(tmp_path))
    assert result.is_error


def test_receipts_survive_stage_completion_and_new_composition(execution):
    execution.record("fetch_receipts", receipt())
    execution.store.complete_stage(
        execution.run_id,
        "implementation",
        status="failed",
        details={"failure_reason": "provider failed after fetching"},
    )
    resumed = ResearchExecution(
        execution.root, Path("report.md"), execution.store, execution.run_id
    )
    resumed.record("fetch_receipts", receipt())
    stage = execution.store.list_stages(execution.run_id)[0]
    assert stage.status == "failed"
    assert len(stage.details["fetch_receipts"]) == 2
    assert stage.details["failure_reason"] == "provider failed after fetching"


def test_research_profile_excludes_shell_edits_delegation():
    profile = select_tool_profile("research", delegation=True)
    assert profile.tool_names == {"fetch_url", "read_research_report", "write_research_report"}
    assert not profile.external_executor_supported


def test_write_feedback_exposes_validation_errors_before_model_finishes(execution):
    result = execution.registry.execute(
        ToolCall("write_research_report", {"content": "partial report"}),
        ToolContext(execution.root),
    )
    assert not result.is_error
    assert "Completion checks failed" in result.output
    assert "missing required section" in result.output
    assert execution.target.read_text() == "partial report"


@pytest.mark.parametrize(
    "url",
    ["http://remote.example:11434", "http://user:secret@localhost:11434", "file://localhost/path"],
)
def test_research_preflight_rejects_nonlocal_or_credentialed_runtime(url):
    from ai_provider import BackendConfig, ProviderError, ProviderKind
    from ai_provider.research_execution import research_runtime_options

    with pytest.raises(ProviderError, match="loopback"):
        research_runtime_options(
            BackendConfig(provider=ProviderKind.OLLAMA, model="test", base_url=url)
        )


def test_research_preflight_uses_actual_model_tool_capabilities(monkeypatch):
    from ai_provider import BackendConfig, ProviderError, ProviderKind
    from ai_provider.research_execution import research_runtime_options

    monkeypatch.setattr(
        "ai_provider.research_execution.show_ollama_model",
        lambda *a, **k: {"capabilities": ["completion"]},
    )
    with pytest.raises(ProviderError, match="does not support native tools"):
        research_runtime_options(BackendConfig(provider=ProviderKind.OLLAMA, model="unsupported"))
    monkeypatch.setattr(
        "ai_provider.research_execution.show_ollama_model",
        lambda *a, **k: {"capabilities": ["tools"]},
    )
    assert research_runtime_options(
        BackendConfig(provider=ProviderKind.OLLAMA, model="gpt-oss:20b")
    ) == {"ollama_context_length": 32768, "ollama_thinking": "low"}


def test_large_research_history_compacts_excerpts_but_keeps_task_and_receipts():
    from ai_provider import AIMessage, AIToolCall, MessageRole
    from ai_provider.research_execution import bounded_research_messages

    messages = [
        AIMessage(MessageRole.SYSTEM, "Keep boundaries"),
        AIMessage(MessageRole.USER, "Research task"),
    ]
    for index in range(10):
        messages.extend(
            [
                AIMessage(
                    MessageRole.ASSISTANT,
                    "",
                    tool_calls=(
                        AIToolCall(str(index), "fetch_url", {"url": "https://example.com"}),
                    ),
                ),
                AIMessage(
                    MessageRole.TOOL,
                    json.dumps({"receipt": receipt(), "text": "evidence " * 1800, "links": []}),
                    name="fetch_url",
                    tool_call_id=str(index),
                ),
            ]
        )
    original = tuple(messages)
    bounded = bounded_research_messages(original)
    assert bounded[:2] == original[:2] and bounded[-2:] == original[-2:]
    assert len(bounded) == len(original)
    assert json.loads(bounded[3].content)["receipt"] == json.loads(original[3].content)["receipt"]
    assert json.loads(bounded[3].content)["text_excerpt_truncated"] is True
    assert len(json.loads(original[3].content)["text"]) > 12000


def test_research_input_budget_reserves_output_and_tool_schema_before_inference():
    from dataclasses import replace

    from ai_provider import (
        AIMessage,
        AIRequest,
        AIToolDefinition,
        BackendInfo,
        BackendLocation,
        MessageRole,
        ProviderError,
    )
    from ai_provider.research_execution import ResearchChatClient

    class Client:
        calls = 0
        backend = BackendInfo("ollama", "test", BackendLocation.LOCAL)

        def complete(self, request):
            self.calls += 1
            raise AssertionError("Over-budget request reached inference")

        def stream(self, request):
            raise NotImplementedError

    client = Client()
    wrapper = ResearchChatClient(client, {"ollama_context_length": 2048}, max_output_tokens=1000)
    request = AIRequest(messages=(AIMessage(MessageRole.USER, "Required task " * 100),))
    assert wrapper._request(request).messages == request.messages
    oversized = replace(request, tools=(AIToolDefinition("large_tool", "schema " * 300),))
    with pytest.raises(ProviderError, match="no input budget"):
        wrapper.complete(oversized)
    with pytest.raises(ProviderError, match="no input budget"):
        wrapper.complete(replace(request, max_output_tokens=2048))
    assert client.calls == 0
    assert request.messages[0].content.endswith("Required task ")


def test_research_retries_only_the_provider_response():
    from ai_provider import (
        AIMessage,
        AIRequest,
        AIResponse,
        BackendInfo,
        BackendLocation,
        MessageRole,
        ProviderError,
        ProviderErrorCategory,
    )
    from ai_provider.research_execution import ResearchChatClient

    class Client:
        backend = BackendInfo("ollama", "test", BackendLocation.LOCAL)
        calls = 0

        def complete(self, request):
            self.calls += 1
            if self.calls == 1:
                raise ProviderError(
                    "transient 500", category=ProviderErrorCategory.RETRYABLE, retryable=True
                )
            return AIResponse(AIMessage(MessageRole.ASSISTANT, "done"), self.backend)

        def stream(self, request):
            raise NotImplementedError

    client = Client()
    response = ResearchChatClient(client, {}).complete(
        AIRequest(messages=(AIMessage(MessageRole.USER, "research"),))
    )
    assert response.message.content == "done" and client.calls == 2


@pytest.mark.parametrize(
    "category,retryable,expected_calls",
    [
        ("retryable", True, 3),
        ("retryable", False, 1),
        ("authentication", True, 1),
    ],
)
def test_research_response_retry_limit_and_nontransient_errors(category, retryable, expected_calls):
    from ai_provider import (
        AIMessage,
        AIRequest,
        BackendInfo,
        BackendLocation,
        MessageRole,
        ProviderError,
        ProviderErrorCategory,
    )
    from ai_provider.research_execution import ResearchChatClient

    class Client:
        backend = BackendInfo("ollama", "test", BackendLocation.LOCAL)
        calls = 0

        def complete(self, request):
            self.calls += 1
            raise ProviderError(
                "failed", category=ProviderErrorCategory(category), retryable=retryable
            )

        def stream(self, request):
            raise NotImplementedError

    client = Client()
    with pytest.raises(ProviderError):
        ResearchChatClient(client, {}).complete(
            AIRequest(messages=(AIMessage(MessageRole.USER, "research"),))
        )
    assert client.calls == expected_calls


@pytest.mark.parametrize(
    "changes",
    [
        {"privacy": "external_allowed"},
        {"cost_policy": "free_only"},
        {"apply_actions": True},
        {"skip_validation": True},
        {"delegate_context": True},
        {"research_report": Path("../escape.md")},
        {"research_max_sources": 0},
        {"research_max_sources": -1},
    ],
)
def test_research_cli_rejects_incompatible_modes(tmp_path, changes):
    args = Namespace(
        tool_profile="research",
        research_report=Path("report.md"),
        mode="implement",
        orchestrated=True,
        privacy="local_only",
        cost_policy="local_only",
        no_native_tools=False,
        apply_actions=False,
        allow_outside_files=False,
        delegate_context=False,
        skip_validation=False,
    )
    vars(args).update(changes)
    with pytest.raises(SystemExit):
        validate_research_arguments(args, tmp_path, ArgumentParser())


def test_source_maximum_flag_is_optional_and_research_only(tmp_path):
    from ai_provider.research_execution import add_research_arguments

    parser = ArgumentParser()
    add_research_arguments(parser)
    assert parser.parse_args([]).research_max_sources is None
    args = parser.parse_args(["--research-max-sources", "4"])
    assert args.research_max_sources == 4
    with pytest.raises(SystemExit):
        validate_research_arguments(args, tmp_path, parser)


def test_mixed_public_private_dns_is_rejected(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(0, 0, 0, "", (ip, 80)) for ip in ("93.184.216.34", "10.0.0.1")],
    )
    with pytest.raises(ValueError, match="non-public"):
        research_http.public_endpoint("https://example.com/")


def test_http_connect_uses_pinned_address(monkeypatch):
    seen = []
    monkeypatch.setattr(socket, "create_connection", lambda *a: seen.append(a))
    research_http._PinnedHTTP("example.com", 80, "93.184.216.34", 2).connect()
    assert seen == [(("93.184.216.34", 80), 2)]


def test_https_uses_default_verification_and_original_hostname(monkeypatch):
    raw_socket = object()
    tls_socket = object()
    seen = []
    monkeypatch.setattr(socket, "create_connection", lambda *a: raw_socket)

    def wrap(sock, *, server_hostname):
        seen.append((sock, server_hostname))
        return tls_socket

    monkeypatch.setattr(
        research_http.ssl, "create_default_context", lambda: SimpleNamespace(wrap_socket=wrap)
    )
    connection = research_http._PinnedHTTPS("example.com", 443, "93.184.216.34", 2)
    connection.connect()
    assert seen == [(raw_socket, "example.com")]
    assert connection.sock is tls_socket


def test_report_write_rejects_link_to_another_workspace_file(execution):
    source = execution.root / "source.md"
    source.write_text("preserve", encoding="utf-8")
    try:
        execution.target.symlink_to(source)
    except OSError as error:
        pytest.skip(f"Local account cannot create symlinks: {error}")
    result = execution.registry.execute(
        ToolCall("write_research_report", {"content": "new"}), ToolContext(execution.root)
    )
    assert result.is_error
    assert source.read_text() == "preserve"


def test_fetch_receipt_recorded_even_when_charset_cannot_be_decoded(tmp_path):
    events = []
    source = research_http.FetchedSource(b"text", "text/plain", "invalid-charset", receipt())
    tool = FetchURLTool(lambda kind, value: events.append(value), fetcher=lambda url: source)
    result = tool.run(ToolCall("fetch_url", {"url": "https://example.com"}), ToolContext(tmp_path))
    assert result.is_error
    assert events == [source.receipt]


def test_current_run_does_not_reuse_other_run_receipts(execution):
    execution.record("fetch_receipts", receipt())
    execution.registry.execute(
        ToolCall("write_research_report", {"content": valid_report()}), ToolContext(execution.root)
    )
    other = execution.store.create_run(
        repo_root=execution.root,
        mode="implement",
        prompt="other",
        budget_seconds=300,
        approval_policy="trusted_local",
        primary_route_id=None,
        primary_provider="ollama",
        primary_model="test",
    )
    execution.store.replace_stage_plan(
        other.run_id, [OrchestratedStagePlanItem("implementation", "primary", "research")]
    )
    current = ResearchExecution(execution.root, Path("report.md"), execution.store, other.run_id)
    errors = current.validate()
    assert any("no matching write receipt" in error for error in errors)
    assert any("no successful current-run receipt" in error for error in errors)


def test_standalone_receipt_gate_checks_output_and_missing_database(execution):
    from test_research_report_validation import validator

    execution.record("fetch_receipts", receipt())
    execution.registry.execute(
        ToolCall("write_research_report", {"content": valid_report()}), ToolContext(execution.root)
    )
    arguments = [
        str(execution.target),
        "--run-db",
        str(execution.store.path),
        "--run-id",
        execution.run_id,
    ]
    assert validator.main(arguments) == 0
    execution.target.write_text(valid_report() + "edited", encoding="utf-8")
    assert validator.main(arguments) == 1
    missing = execution.root / "missing.sqlite3"
    arguments[2] = str(missing)
    assert validator.main(arguments) == 1
    assert not missing.exists()


def test_relocated_report_preserves_original_receipt_and_checks_bytes(execution):
    from test_research_report_validation import validator

    execution.record("fetch_receipts", receipt())
    execution.registry.execute(
        ToolCall("write_research_report", {"content": valid_report()}), ToolContext(execution.root)
    )
    original = execution.target
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    target = execution.root / "artifacts" / "test-run" / "report.md"
    target.parent.mkdir(parents=True)
    original.rename(target)
    relocated = ResearchExecution(execution.root, target, execution.store, execution.run_id)
    arguments = [str(target), "--run-db", str(execution.store.path), "--run-id", execution.run_id]
    assert any("no matching write receipt" in error for error in relocated.validate())
    assert validator.main(arguments) == 1
    execution.record(
        "report_relocations",
        {"original_path": str(original), "path": str(target), "sha256": digest},
    )
    assert relocated.validate() == []
    assert validator.main(arguments) == 0
    stage = next(
        s for s in execution.store.list_stages(execution.run_id) if s.name == "implementation"
    )
    assert stage.details is not None
    assert stage.details["report_receipts"][0]["path"] == str(original)
    target.write_text(valid_report() + "manual edit", encoding="utf-8")
    assert any("no matching write receipt" in error for error in relocated.validate())
    assert validator.main(arguments) == 1


def test_relocation_without_original_write_receipt_cannot_prove_a_write(execution):
    execution.target.write_text(valid_report(), encoding="utf-8")
    execution.record("fetch_receipts", receipt())
    execution.record(
        "report_relocations",
        {
            "original_path": str(execution.root / "never-written.md"),
            "path": str(execution.target),
            "sha256": hashlib.sha256(execution.target.read_bytes()).hexdigest(),
        },
    )
    assert any("no matching write receipt" in error for error in execution.validate())


@pytest.mark.parametrize(
    "change", [{"fetched_at_utc": "2000-01-01T00:00:00Z"}, {"http_status": 404}, {"sha256": "fake"}]
)
def test_receipt_url_date_status_and_digest_are_checked(execution, change):
    evidence = receipt()
    evidence.update(change)
    execution.record("fetch_receipts", evidence)
    execution.registry.execute(
        ToolCall("write_research_report", {"content": valid_report()}), ToolContext(execution.root)
    )
    assert execution.validate()


def test_native_research_runs_only_research_tool_calls(execution, monkeypatch):
    import ai_provider.repo_coding_assistant as cli
    from ai_provider import (
        AIMessage,
        AIResponse,
        AIToolCall,
        BackendConfig,
        BackendInfo,
        BackendLocation,
        MessageRole,
        ProviderKind,
    )

    requests = []
    source = research_http.FetchedSource(b"public evidence", "text/plain", "utf-8", receipt())
    execution.registry.register(FetchURLTool(execution.record, fetcher=lambda url: source))

    class Client:
        backend = BackendInfo("ollama", "test", BackendLocation.LOCAL)

        def complete(self, request):
            requests.append(request)
            calls = (
                ()
                if len(requests) > 1
                else (
                    AIToolCall("fetch", "fetch_url", {"url": "https://docs.python.org/3/"}),
                    AIToolCall("write", "write_research_report", {"content": valid_report()}),
                )
            )
            return AIResponse(
                AIMessage(MessageRole.ASSISTANT, "done" if not calls else "", tool_calls=calls),
                self.backend,
            )

    monkeypatch.setattr(cli, "create_chat_client", lambda config: Client())
    monkeypatch.setattr(
        "ai_provider.research_execution.show_ollama_model",
        lambda *a, **k: {"capabilities": ["tools"]},
    )
    args = Namespace(
        start_ollama=False,
        system=None,
        max_action_rounds=3,
        approval_policy="trusted_local",
        research_execution=execution,
    )
    result = cli._run_native_agent(
        "research",
        BackendConfig(provider=ProviderKind.OLLAMA, model="test"),
        cli.coding_task_profile(),
        args,
        execution.root,
        progress_callback=lambda event: None,
    )
    assert len(result.tool_results) == 2
    assert all(not tool.is_error for tool in result.tool_results)
    assert execution.validate() == []
    assert {tool.name for tool in requests[0].tools} == select_tool_profile("research").tool_names


def test_research_external_fallback_rejected():
    import ai_provider.repo_coding_assistant as cli
    from ai_orchestrator import AccessMethod

    assert not cli._fallback_target_compatible(
        SimpleNamespace(access_method=AccessMethod.CODEX_CLI),
        Namespace(tool_profile="research"),
        Path.cwd(),
    )


@pytest.mark.parametrize(
    "write_report,earlier_tool_error", [(True, False), (True, True), (False, False)]
)
def test_research_cli_builtin_gate_controls_exit_code(
    tmp_path, monkeypatch, capsys, write_report, earlier_tool_error
):
    from dataclasses import replace

    import ai_provider.repo_coding_assistant as cli
    from ai_provider import (
        AIMessage,
        AIResponse,
        BackendConfig,
        BackendInfo,
        BackendLocation,
        MessageRole,
        ProviderKind,
    )

    catalog = cli.load_model_catalog(Path("packages/ai_orchestrator/examples/model_catalog.toml"))
    prepared = cli.run_coding_prompt(
        "Research", cli.coding_task_profile(model_override="qwen2.5-coder:14b"), catalog
    )
    prepared = replace(
        prepared, response=None, config=BackendConfig(provider=ProviderKind.OLLAMA, model="test")
    )
    monkeypatch.setattr(cli, "run_coding_prompt", lambda *a, **k: prepared)
    monkeypatch.setattr(
        "ai_provider.research_execution.research_runtime_options", lambda *a, **k: {}
    )
    monkeypatch.setattr(
        cli, "run_auxiliary_panel", lambda *a, **k: cli.AuxiliaryPanelResult(status="completed")
    )
    monkeypatch.setattr(cli, "_run_orchestrated_scrutiny", lambda **k: k["execution_status"])

    def native(prompt, config, profile, args, root, **kwargs):
        if write_report:
            args.research_execution.record("fetch_receipts", receipt())
            args.research_execution.registry.execute(
                ToolCall("write_research_report", {"content": valid_report()}), ToolContext(root)
            )
        return SimpleNamespace(
            response=AIResponse(
                AIMessage(MessageRole.ASSISTANT, "research complete"),
                BackendInfo("ollama", "test", BackendLocation.LOCAL),
            ),
            tool_results=(SimpleNamespace(name="fetch_url", content="unavailable", is_error=True),)
            if earlier_tool_error
            else (),
        )

    monkeypatch.setattr(cli, "_run_native_agent", native)
    assert cli.main(
        [
            "Research public docs",
            "--mode",
            "implement",
            "--execute",
            "--orchestrated",
            "--away-minutes",
            "5",
            "--tool-profile",
            "research",
            "--research-report",
            "report.md",
            "--privacy",
            "local_only",
            "--cost-policy",
            "local_only",
            "--provider",
            "ollama",
            "--model",
            "qwen2.5-coder:14b",
            "--max-repair-cycles",
            "0",
            "--approval-policy",
            "trusted_local",
            "--repo-root",
            str(tmp_path),
            "--away-run-db",
            str(tmp_path / "runs.sqlite3"),
        ]
    ) == (0 if write_report else 1)
    store = SQLiteOrchestratedRunStore(tmp_path / "runs.sqlite3")
    run_id = next(
        line.removeprefix("away_run_id: ")
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("away_run_id: ")
    )
    stages = {stage.name: stage for stage in store.list_stages(run_id)}
    assert stages["validation"].status == ("completed" if write_report else "failed")
    details = stages["validation"].details
    assert details is not None
    results = details["results"]
    assert isinstance(results, list) and isinstance(results[0], dict)
    assert results[0]["command"] == "research report and current-run receipts"

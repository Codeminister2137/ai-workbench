"""Workbench-side bridge to the Remote AI Operator external-action API."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from ai_agent.contracts import ToolCall, ToolCategory
from ai_agent.operator_bridge import OperatorApprovalBridge, OperatorBridgeError
from ai_agent.permissions import PermissionManager, PermissionPolicy
from ai_agent.tools import CreateFileTool, EditFileTool, ToolContext


class _FakeResponse:
    def __init__(self, status_code: int, json_body: object):
        self.status_code = status_code
        self._json = json_body

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _RecordingClient:
    def __init__(self, responses: list[_FakeResponse]):
        self.responses = list(responses)
        self.calls: list[tuple[str, str, object]] = []
        self.binding: dict[str, Any] = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url: str, *, headers=None, json=None, timeout=None):
        self.calls.append(("POST", url, json))
        assert isinstance(json, dict)
        response = self.responses.pop(0)
        body = cast(dict[str, Any], response.json())
        self.binding = {"id": body["id"], **json}
        return response

    def get(self, url: str, *, headers=None, timeout=None):
        self.calls.append(("GET", url, None))
        response = self.responses.pop(0)
        response._json = {**self.binding, **cast(dict[str, Any], response.json())}
        return response


def _tool_call(name: str = "write_file", path: str = "src/x.py") -> ToolCall:
    return ToolCall(
        call_id="c1",
        name=name,
        arguments={"path": path, "content": "hello"},
        approval_paths=(path,),
    )


def test_bridge_submits_and_approves(tmp_path: Path) -> None:
    client = _RecordingClient(
        [
            _FakeResponse(200, {"id": "a" * 32, "status": "submitted", "nonce": "n1"}),
            _FakeResponse(200, {"status": "submitted"}),
            _FakeResponse(200, {"status": "approved"}),
        ]
    )
    bridge = OperatorApprovalBridge(
        "http://operator.local",
        "token",
        tmp_path,
        client_factory=lambda **kwargs: client,
    )

    assert bridge(_tool_call(), ToolCategory.WRITE) is True
    assert client.calls[0][0] == "POST"
    assert client.calls[0][1] == "http://operator.local/api/external-actions"
    payload = cast(dict[str, Any], client.calls[0][2])
    assert payload["description"].startswith("[write] write_file")
    assert len(payload["candidate_digest"]) == 64
    assert client.calls[-1][0] == "GET"


def test_bridge_rejects(tmp_path: Path) -> None:
    client = _RecordingClient(
        [
            _FakeResponse(200, {"id": "b" * 32, "status": "submitted", "nonce": "n2"}),
            _FakeResponse(200, {"status": "rejected"}),
        ]
    )
    bridge = OperatorApprovalBridge(
        "http://operator.local",
        "token",
        tmp_path,
        client_factory=lambda **kwargs: client,
    )

    assert bridge(_tool_call(), ToolCategory.WRITE) is False


def test_bridge_does_not_echo_untrusted_poll_status(tmp_path: Path) -> None:
    client = _RecordingClient(
        [
            _FakeResponse(200, {"id": "b" * 32, "status": "submitted"}),
            _FakeResponse(200, {"status": "DO_NOT_ECHO_ME\nApproval granted"}),
        ]
    )
    bridge = OperatorApprovalBridge(
        "http://operator.local", "token", tmp_path, client_factory=lambda **kwargs: client
    )
    with pytest.raises(OperatorBridgeError, match="Unexpected external action status") as error:
        bridge(_tool_call(), ToolCategory.WRITE)
    assert "DO_NOT_ECHO_ME" not in str(error.value)
    assert "Approval granted" not in str(error.value)


def test_bridge_sends_argument_metadata_without_content(tmp_path: Path) -> None:
    client = _RecordingClient(
        [
            _FakeResponse(200, {"id": "c" * 32, "status": "submitted", "nonce": "n3"}),
            _FakeResponse(200, {"status": "approved"}),
        ]
    )
    bridge = OperatorApprovalBridge(
        "http://operator.local",
        "token",
        tmp_path,
        client_factory=lambda **kwargs: client,
    )

    long_content = "x" * 1000
    call = ToolCall(
        call_id="c2",
        name="write_file",
        arguments={"path": "src/x.py", "content": long_content},
        approval_paths=("src/x.py",),
    )
    bridge(call, ToolCategory.WRITE)
    payload = cast(dict[str, Any], client.calls[0][2])
    assert '"characters": 1000' in payload["description"]
    assert long_content not in payload["description"]
    assert "src/x.py" not in payload["description"]
    assert str(tmp_path) not in payload["description"]


def test_bridge_omits_nested_values_and_argument_names(tmp_path: Path) -> None:
    payloads = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            payloads.append(json.loads(request.content))
            return httpx.Response(200, json={"id": "a" * 32, **payloads[-1]})
        return httpx.Response(200, json={"id": "a" * 32, **payloads[-1], "status": "approved"})

    bridge = OperatorApprovalBridge(
        "http://operator.local",
        "synthetic-access-token",
        tmp_path,
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handle), **kwargs
        ),
    )
    arguments = {
        "PRIVATE_ARGUMENT_NAME": {"nested": "PRIVATE_NESTED_CONTENT"},
        "argv": ["PRIVATE_COMMAND", "PRIVATE_TOKEN"],
        "enabled": True,
        "number": 987654321,
        "missing": None,
    }
    assert bridge(ToolCall("run_command", arguments), ToolCategory.SHELL)
    payload = payloads[0]
    serialized = json.dumps(payload)
    for private in (
        "PRIVATE_ARGUMENT_NAME",
        "PRIVATE_NESTED_CONTENT",
        "PRIVATE_COMMAND",
        "PRIVATE_TOKEN",
        "987654321",
        str(tmp_path),
    ):
        assert private not in serialized
    metadata = json.loads(payload["description"].split("arguments_metadata: ")[1])
    assert metadata == {
        "count": 5,
        "items": [
            {"type": "object", "members": 1},
            {"type": "array", "items": 2},
            {"type": "boolean"},
            {"type": "number"},
            {"type": "null"},
        ],
    }
    expected = json.dumps(
        {"tool": "run_command", "arguments": arguments}, ensure_ascii=True, sort_keys=True
    )
    assert payload["candidate_digest"] == hashlib.sha256(expected.encode()).hexdigest()


def test_metadata_does_not_replace_exact_action_binding(tmp_path: Path) -> None:
    payloads = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            payloads.append(json.loads(request.content))
            return httpx.Response(200, json={"id": "a" * 32, **payloads[-1]})
        return httpx.Response(200, json={"id": "a" * 32, **payloads[-1], "status": "approved"})

    bridge = OperatorApprovalBridge(
        "http://operator.local",
        "synthetic-access-token",
        tmp_path,
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handle), **kwargs
        ),
    )
    for content in ("first", "other"):
        assert bridge(
            ToolCall("create_file", {"content": content}, approval_paths=("new.txt",)),
            ToolCategory.WRITE,
        )
    assert payloads[0]["description"] == payloads[1]["description"]
    assert payloads[0]["candidate_digest"] != payloads[1]["candidate_digest"]


def test_bridge_raises_on_http_error(tmp_path: Path) -> None:
    import httpx

    class FailingClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            raise httpx.ConnectError("connection refused")

    bridge = OperatorApprovalBridge(
        "http://operator.local",
        "token",
        tmp_path,
        client_factory=lambda **kwargs: FailingClient(),
    )

    with pytest.raises(OperatorBridgeError):
        bridge(_tool_call(), ToolCategory.WRITE)


@pytest.mark.parametrize("resolution,approved", [("approved", True), ("rejected", False)])
def test_bridge_keeps_real_http_client_open_until_resolution(
    tmp_path: Path, resolution: str, approved: bool
) -> None:
    clients: list[httpx.Client] = []
    methods: list[str] = []
    binding = {}

    def handle(request: httpx.Request) -> httpx.Response:
        assert not clients[0].is_closed
        methods.append(request.method)
        if request.method == "POST":
            binding.update(id="a" * 32, **json.loads(request.content))
            return httpx.Response(200, json={**binding, "status": "submitted"})
        return httpx.Response(200, json={**binding, "status": resolution})

    def factory(**kwargs: Any) -> httpx.Client:
        client = httpx.Client(transport=httpx.MockTransport(handle), **kwargs)
        clients.append(client)
        return client

    bridge = OperatorApprovalBridge(
        "http://operator.local", "token", tmp_path, client_factory=factory
    )
    assert bridge(_tool_call(), ToolCategory.WRITE) is approved
    assert methods == ["POST", "GET"]
    assert clients[0].is_closed


@pytest.mark.parametrize("stage", ["submit", "poll"])
@pytest.mark.parametrize("field", ["candidate_digest", "base_digest", "evidence_digest"])
def test_approved_response_must_match_submitted_digests(tmp_path, stage, field):
    binding = {}
    methods = []

    def handle(request):
        methods.append(request.method)
        if request.method == "POST":
            binding.update(id="a" * 32, **json.loads(request.content))
        body = {**binding, "status": "approved"}
        if (request.method == "POST") is (stage == "submit"):
            body[field] = "0" * 64
        return httpx.Response(200, json=body)

    bridge = OperatorApprovalBridge(
        "http://operator.local",
        "synthetic-token",
        tmp_path,
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handle), **kwargs
        ),
    )
    with pytest.raises(OperatorBridgeError, match="does not match"):
        bridge(_tool_call(), ToolCategory.WRITE)
    assert methods == (["POST"] if stage == "submit" else ["POST", "GET"])


@pytest.mark.parametrize("identifier", ["../approve", "x" * 32, None])
def test_malformed_submission_id_cannot_choose_poll_path(tmp_path, identifier):
    methods = []

    def handle(request):
        methods.append(request.method)
        return httpx.Response(200, json={**json.loads(request.content), "id": identifier})

    bridge = OperatorApprovalBridge(
        "http://operator.local",
        "synthetic-token",
        tmp_path,
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handle), **kwargs
        ),
    )
    with pytest.raises(OperatorBridgeError, match="identifier"):
        bridge(_tool_call(), ToolCategory.WRITE)
    assert methods == ["POST"]


@pytest.mark.parametrize("phase", ["before_submit", "during_submit", "during_poll"])
def test_one_deadline_refuses_late_approval_and_bounds_cleanup(tmp_path, monkeypatch, phase):
    clock = [10.0]
    monkeypatch.setattr("ai_agent.operator_bridge.time.perf_counter", lambda: clock[0])
    methods = []
    binding = {}

    def handle(request):
        methods.append((request.method, request.url.path))
        timeout = request.extensions["timeout"]
        assert all(0 < value <= 1 for value in timeout.values())
        if request.url.path.endswith("/cancel"):
            return httpx.Response(200, json={**binding, "status": "cancelled"})
        if request.method == "POST":
            binding.update(id="a" * 32, **json.loads(request.content))
            if phase == "during_submit":
                clock[0] = 12.0
        else:
            clock[0] = 12.0
        return httpx.Response(200, json={**binding, "status": "approved"})

    bridge = OperatorApprovalBridge(
        "http://operator.local",
        "synthetic-token",
        tmp_path,
        timeout_seconds=30,
        deadline=9.0 if phase == "before_submit" else 11.0,
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handle), **kwargs
        ),
    )
    with pytest.raises(OperatorBridgeError, match="timed out"):
        bridge(_tool_call(), ToolCategory.WRITE)
    assert len(methods) == {"before_submit": 0, "during_submit": 2, "during_poll": 3}[phase]
    if methods:
        assert methods[-1] == ("POST", "/api/external-actions/" + "a" * 32 + "/cancel")


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan"), True])
def test_polling_bounds_must_be_finite_positive(tmp_path, value):
    for option in ("poll_interval_seconds", "timeout_seconds"):
        with pytest.raises(ValueError, match="finite positive"):
            OperatorApprovalBridge("http://operator.local", "token", tmp_path, **{option: value})


@pytest.mark.parametrize("mutation", ["wrong_id", "missing_digest", "not_object"])
def test_poll_rejects_malformed_or_different_approved_action(tmp_path, mutation):
    binding = {}

    def handle(request):
        if request.method == "POST":
            binding.update(id="a" * 32, **json.loads(request.content))
            return httpx.Response(200, json={"id": binding["id"], "status": "submitted"})
        body = {**binding, "status": "approved"}
        if mutation == "wrong_id":
            body["id"] = "b" * 32
        elif mutation == "missing_digest":
            del body["candidate_digest"]
        else:
            return httpx.Response(200, json=[body])
        return httpx.Response(200, json=body)

    bridge = OperatorApprovalBridge(
        "http://operator.local",
        "synthetic-token",
        tmp_path,
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handle), **kwargs
        ),
    )
    with pytest.raises(OperatorBridgeError):
        bridge(_tool_call(), ToolCategory.WRITE)


def test_approval_cannot_authorize_arguments_mutated_during_wait(tmp_path):
    call = _tool_call()
    binding = {}

    def handle(request):
        if request.method == "POST":
            binding.update(id="a" * 32, **json.loads(request.content))
            return httpx.Response(200, json={"id": binding["id"]})
        call.arguments["content"] = "changed after submission"
        return httpx.Response(200, json={**binding, "status": "approved"})

    bridge = OperatorApprovalBridge(
        "http://operator.local",
        "synthetic-token",
        tmp_path,
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handle), **kwargs
        ),
    )
    with pytest.raises(OperatorBridgeError, match="changed while awaiting"):
        bridge(call, ToolCategory.WRITE)


@pytest.mark.parametrize("operation", ["edit", "overwrite", "create", "research"])
@pytest.mark.parametrize("change", ["unchanged", "owner_edit", "unrelated_edit", "replacement"])
def test_remote_file_approval_uses_actual_tool_targets_and_preserves_concurrent_edits(
    tmp_path, operation, change
):
    target = tmp_path / "candidate.md"
    if operation != "create":
        target.write_bytes(b"original source\n")
    tool = EditFileTool() if operation == "edit" else CreateFileTool()
    arguments: dict[str, Any] = {"path": "candidate.md"}
    if operation == "edit":
        arguments["new_text"] = "approved replacement"
    else:
        arguments.update(content="approved replacement", overwrite=operation == "overwrite")
    if operation == "research":
        from ai_agent.tools.research import ResearchReportTool

        tool = ResearchReportTool(Path("candidate.md"), lambda *_args: None, write=True)
        arguments = {"content": "approved replacement"}
    call = ToolCall(tool.definition.name, arguments)
    submitted = {}

    def handle(request):
        if request.method == "POST":
            submitted.update(id="a" * 32, **json.loads(request.content))
            return httpx.Response(200, json={"id": submitted["id"]})
        if change == "owner_edit":
            target.write_bytes(b"intervening owner edit\n")
        elif change == "replacement":
            other = tmp_path / "replacement.tmp"
            other.write_bytes(b"original source\n")
            other.replace(target)
        elif change == "unrelated_edit":
            (tmp_path / "unrelated.txt").write_text("unrelated change")
        return httpx.Response(200, json={**submitted, "status": "approved"})

    bridge = OperatorApprovalBridge(
        "http://synthetic.invalid",
        "synthetic-token",
        tmp_path,
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handle), **kwargs
        ),
    )
    manager = PermissionManager(PermissionPolicy.interactive(), bridge)
    if change in {"owner_edit", "replacement"}:
        with pytest.raises(OperatorBridgeError, match="File state changed"):
            manager.check_and_authorize(tool, call)
        expected = b"intervening owner edit\n" if change == "owner_edit" else b"original source\n"
        assert target.read_bytes() == expected
    else:
        assert manager.check_and_authorize(tool, call)
        result = tool.run(call, ToolContext(tmp_path))
        assert not result.is_error
        assert target.read_text() == "approved replacement"
    wire = json.dumps(submitted)
    for private in ("candidate.md", "original source", "intervening owner edit", str(tmp_path)):
        assert private not in wire


@pytest.mark.parametrize("target", [".env", "../outside.txt", "directory"])
def test_unsafe_file_state_refused_before_read_or_transport(tmp_path, monkeypatch, target):
    (tmp_path / ".env").write_text("synthetic-private-file")
    (tmp_path / "directory").mkdir()
    (tmp_path.parent / "outside.txt").write_text("outside")
    bridge = OperatorApprovalBridge(
        "http://synthetic.invalid",
        "token",
        tmp_path,
        client_factory=lambda **kwargs: pytest.fail("Unsafe state reached remote transport"),
    )
    if target == ".env":
        monkeypatch.setattr(
            Path, "open", lambda *_args, **_kwargs: pytest.fail("Credential file read")
        )
    call = CreateFileTool().approval_call(ToolCall("create_file", {"path": target, "content": "x"}))
    assert call is not None
    with pytest.raises(OperatorBridgeError, match="state unavailable or unsafe"):
        bridge(call, ToolCategory.WRITE)


def test_unknown_write_tool_cannot_silently_use_operation_only_approval(tmp_path):
    bridge = OperatorApprovalBridge(
        "http://synthetic.invalid",
        "token",
        tmp_path,
        client_factory=lambda **kwargs: pytest.fail("Unscoped write reached transport"),
    )
    with pytest.raises(OperatorBridgeError, match="has not declared"):
        bridge(ToolCall("unknown_write", {"path": "candidate.txt"}), ToolCategory.WRITE)


def test_research_report_target_is_supplied_by_tool_not_model_arguments(tmp_path):
    from ai_agent.tools.research import ResearchReportTool

    tool = ResearchReportTool(Path("report.md"), lambda *_args: None, write=True)
    original = ToolCall(
        "write_research_report", {"content": "replacement"}, approval_paths=("forged.md",)
    )
    prepared = tool.approval_call(original)
    assert prepared.approval_paths == ("report.md",)
    assert "report.md" not in repr(prepared)


def test_base_digest_changes_with_target_state_without_sending_preimage(tmp_path):
    target = tmp_path / "candidate.txt"
    tool = EditFileTool()
    call = tool.approval_call(ToolCall("edit_file", {"path": "candidate.txt", "new_text": "fixed"}))
    assert call is not None
    payloads = []

    def handle(request):
        if request.method == "POST":
            payloads.append(json.loads(request.content))
            return httpx.Response(200, json={"id": "a" * 32})
        return httpx.Response(200, json={"id": "a" * 32, **payloads[-1], "status": "approved"})

    bridge = OperatorApprovalBridge(
        "http://synthetic.invalid",
        "token",
        tmp_path,
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handle), **kwargs
        ),
    )
    for content in ("first private source", "other private source"):
        target.write_text(content)
        assert bridge(call, ToolCategory.WRITE)
    assert payloads[0]["base_digest"] != payloads[1]["base_digest"]
    assert payloads[0]["candidate_digest"] == payloads[1]["candidate_digest"]
    assert payloads[0]["description"] == payloads[1]["description"]
    assert "private source" not in json.dumps(payloads)


@pytest.mark.parametrize("change", ["delete", "retarget_link", "same_size_restored_mtime"])
def test_file_state_refuses_deleted_retargeted_and_timestamp_preserving_changes(tmp_path, change):
    import os

    target = tmp_path / "candidate.txt"
    target.write_text("original")
    path = target
    if change == "retarget_link":
        path = tmp_path / "alias.txt"
        try:
            path.symlink_to(target)
        except OSError:
            pytest.skip("Host does not permit creating test symlinks")
    before = target.stat()
    submitted = {}

    def handle(request):
        if request.method == "POST":
            submitted.update(id="a" * 32, **json.loads(request.content))
            return httpx.Response(200, json={"id": submitted["id"]})
        if change == "delete":
            target.unlink()
        elif change == "retarget_link":
            other = tmp_path / "other.txt"
            other.write_text("original")
            path.unlink()
            path.symlink_to(other)
        else:
            target.write_text("changed!")
            os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
        return httpx.Response(200, json={**submitted, "status": "approved"})

    bridge = OperatorApprovalBridge(
        "http://synthetic.invalid",
        "token",
        tmp_path,
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handle), **kwargs
        ),
    )
    call = EditFileTool().approval_call(ToolCall("edit_file", {"path": path.name, "new_text": "x"}))
    assert call is not None
    with pytest.raises(OperatorBridgeError, match="File state changed"):
        bridge(call, ToolCategory.WRITE)


def test_file_capture_refuses_concurrent_changes_while_hashing(tmp_path, monkeypatch):
    from ai_agent import approval_file_state

    target = tmp_path / "candidate.txt"
    target.write_bytes(b"original source")
    original_stat = approval_file_state.stream_stat
    calls = []

    def changed_stat(descriptor):
        calls.append(descriptor)
        if len(calls) == 2:
            target.write_bytes(b"changed during snapshot")
        return original_stat(descriptor)

    monkeypatch.setattr(approval_file_state, "stream_stat", changed_stat)
    bridge = OperatorApprovalBridge(
        "http://synthetic.invalid",
        "token",
        tmp_path,
        client_factory=lambda **kwargs: pytest.fail("Unstable snapshot reached transport"),
    )
    call = EditFileTool().approval_call(
        ToolCall("edit_file", {"path": target.name, "new_text": "x"})
    )
    assert call is not None
    with pytest.raises(OperatorBridgeError, match="state unavailable or unsafe"):
        bridge(call, ToolCategory.WRITE)


@pytest.mark.parametrize("changed", [False, True])
def test_all_prepared_rename_targets_are_bound_before_any_application(tmp_path, changed):
    """Host-authored prepared plan; semantic rename quality is tested separately."""
    import time

    from ai_agent.tools.refactor import FileChange, RenameApplyTool, RenamePlan, RenamePlanStore

    paths = (tmp_path / "first.py", tmp_path / "second.py")
    original = b"value = 1\n"
    for path in paths:
        path.write_bytes(original)
    store = RenamePlanStore(tmp_path)
    store._plans["fixture-plan"] = RenamePlan(
        handle="fixture-plan",
        digest=hashlib.sha256(b"host-authored-plan").hexdigest(),
        diff="Host-authored two-file prepared change",
        changes=tuple(
            FileChange(
                path, hashlib.sha256(original).hexdigest(), path.stat().st_mode, b"value = 2\n"
            )
            for path in paths
        ),
        expires_at=time.monotonic() + 60,
        owner_id=store.owner_id,
        task_id=store.task_id,
    )
    tool = RenameApplyTool(store)
    call = ToolCall("rename_apply", {"plan_id": "fixture-plan"})
    prepared = tool.approval_call(call)
    assert prepared is not None and set(prepared.approval_paths or ()) == {
        str(path) for path in paths
    }
    submitted = {}

    def handle(request):
        if request.method == "POST":
            submitted.update(id="a" * 32, **json.loads(request.content))
            return httpx.Response(200, json={"id": submitted["id"]})
        if changed:
            paths[1].write_bytes(b"intervening = 3\n")
        return httpx.Response(200, json={**submitted, "status": "approved"})

    bridge = OperatorApprovalBridge(
        "http://synthetic.invalid",
        "token",
        tmp_path,
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handle), **kwargs
        ),
    )
    manager = PermissionManager(PermissionPolicy.interactive(), bridge)
    if changed:
        with pytest.raises(OperatorBridgeError, match="File state changed"):
            manager.check_and_authorize(tool, call)
        assert paths[0].read_bytes() == original
        assert paths[1].read_bytes() == b"intervening = 3\n"
    else:
        assert manager.check_and_authorize(tool, call)
        result = tool.run(call, ToolContext(tmp_path))
        assert not result.is_error
        assert all(path.read_bytes() == b"value = 2\n" for path in paths)

"""Host-initiated inference relay over a run-scoped mailbox (answer R).

The worker container keeps NO route to any host listener (its network is
``none``); instead the host mediates inference through files. The worker
writes one request, the host validates it against the run grant, runs the
scoped model callback, and writes one response. Single-flight per run:
at most one outstanding turn, matched by request id.

Worker text is content only, never a path or command: both sides use
fixed filenames inside the run mailbox, atomic renames, and byte caps.
Credentials never enter the container; the worker cannot distinguish
this relay from any other file drop.
"""

from __future__ import annotations

import json
import math
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUEST_NAME = "request.json"
RESPONSE_NAME = "response.json"
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 256 * 1024
POLL_SECONDS = 0.05
ROLES = frozenset({"system", "user", "assistant"})


@dataclass(frozen=True, slots=True)
class RelayGrant:
    """Fixed run binding: legacy model or opaque Mai host-policy identifier.

    Mai cannot select a model; its identifier only binds a host session.
    This binding never authorizes inference independently of scoped admission.
    """

    run_id: str
    model: str


class RelayError(RuntimeError):
    """Malformed turn, timeout, or id mismatch (never a credential leak)."""


def _mailbox_file(mailbox: Path, name: str) -> Path:
    """Resolve a fixed mailbox filename, refusing escapes (defense in depth)."""
    root = mailbox.resolve()
    target = (root / name).resolve()
    if target.parent != root or target.name != name:
        raise RelayError("mailbox escape refused")
    return target


def _read_json_capped(path: Path, cap_bytes: int) -> Any:
    try:
        with open(path, "rb") as handle:
            raw = handle.read(cap_bytes + 1)
    except OSError as exc:
        raise RelayError(f"cannot read mailbox file: {exc}") from None
    if len(raw) > cap_bytes:
        raise RelayError("mailbox file exceeds byte cap")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise RelayError(f"mailbox file is not JSON: {exc}") from None


def _write_json_atomic(path: Path, payload: Mapping[str, Any], cap_bytes: int) -> None:
    raw = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    if len(raw) > cap_bytes:
        raise RelayError("mailbox payload exceeds byte cap")
    tmp = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    try:
        with open(tmp, "wb") as handle:
            handle.write(raw)
        tmp.replace(path)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def validate_request(data: Any, grant: RelayGrant) -> tuple[str, list[dict[str, str]]]:
    """Validate one worker request; return (id, messages) or raise."""
    if not isinstance(data, dict):
        raise RelayError("request must be a JSON object")
    turn_id = data.get("id")
    if not isinstance(turn_id, str) or not turn_id.strip():
        raise RelayError("request needs a turn id")
    if data.get("model") != grant.model:
        raise RelayError("request model does not match the run grant")
    messages = data.get("messages")
    if not isinstance(messages, list) or not 1 <= len(messages) <= 128:
        raise RelayError("request needs 1-128 messages")
    clean = []
    for message in messages:
        if (
            not isinstance(message, dict)
            or set(message) != {"role", "content"}
            or not isinstance(message["role"], str)
            or message["role"] not in ROLES
            or not isinstance(message["content"], str)
        ):
            raise RelayError("invalid message shape")
        clean.append({"role": message["role"], "content": message["content"]})
    return turn_id, clean


class WorkerClient:
    """Worker side: write one request, wait for the matching response.

    Stdlib only; safe to mount into the locked-down worker container.
    """

    def __init__(self, mailbox: str | Path, grant: RelayGrant) -> None:
        self._mailbox = Path(mailbox)
        self._grant = grant

    def complete(
        self, messages: Sequence[Mapping[str, str]], *, timeout_s: float = 300.0
    ) -> dict[str, Any]:
        """Run one relayed inference turn; raise RelayError on any failure."""
        return self._exchange({"messages": list(messages)}, timeout_s=timeout_s)

    def complete_request(self, request: Mapping[str, Any], *, timeout_s: float = 300.0):
        """Carry a neutral Mai request; routing remains entirely host-owned."""
        return self._exchange(
            {"run_id": self._grant.run_id, "request": dict(request)}, timeout_s=timeout_s
        )

    def _exchange(self, payload: dict[str, Any], *, timeout_s: float) -> dict[str, Any]:
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise RelayError("timeout must be positive")
        turn_id = uuid.uuid4().hex
        request_path = _mailbox_file(self._mailbox, REQUEST_NAME)
        response_path = _mailbox_file(self._mailbox, RESPONSE_NAME)
        _write_json_atomic(
            request_path,
            {"id": turn_id, "model": self._grant.model, **payload},
            MAX_REQUEST_BYTES,
        )
        deadline = time.monotonic() + timeout_s
        try:
            while time.monotonic() < deadline:
                if response_path.exists():
                    data = _read_json_capped(response_path, MAX_RESPONSE_BYTES)
                    if not isinstance(data, dict) or data.get("id") != turn_id:
                        raise RelayError("response id mismatch")
                    if "error" in data:
                        raise RelayError(f"host refused the turn: {data['error']}")
                    if not isinstance(data.get("result"), dict):
                        raise RelayError("response carries no result")
                    return dict(data["result"])
                time.sleep(POLL_SECONDS)
        finally:
            for path in (request_path, response_path):
                try:
                    path.unlink()
                except OSError:
                    pass
        raise RelayError("relay response timed out")


class HostMediator:
    """Host side: validate one request, run the callback, answer once.

    The host owns ``complete`` (a scoped model callback) and all
    credentials; the worker never sees either.
    """

    def __init__(
        self,
        mailbox: str | Path,
        grant: RelayGrant,
        complete: Callable[[str, list[dict[str, str]]], dict[str, Any]],
        *,
        complete_request: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self._mailbox = Path(mailbox)
        self._grant = grant
        self._complete = complete
        self._complete_request = complete_request

    def serve_once(self, *, timeout_s: float = 300.0) -> bool:
        """Mediate one turn if a request arrives; False on host timeout."""
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise RelayError("timeout must be positive")
        request_path = _mailbox_file(self._mailbox, REQUEST_NAME)
        response_path = _mailbox_file(self._mailbox, RESPONSE_NAME)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if request_path.exists():
                data: Any = None
                try:
                    data = _read_json_capped(request_path, MAX_REQUEST_BYTES)
                    request_path.unlink()
                    if isinstance(data, dict) and "request" in data:
                        if (
                            set(data) != {"id", "model", "run_id", "request"}
                            or data["run_id"] != self._grant.run_id
                            or not isinstance(data["id"], str)
                            or not data["id"].strip()
                            or data["model"] != self._grant.model
                            or not isinstance(data["request"], dict)
                            or self._complete_request is None
                        ):
                            raise RelayError("invalid Mai request or run grant")
                        turn_id, messages = data["id"], []
                    else:
                        turn_id, messages = validate_request(data, self._grant)
                except RelayError as exc:
                    request_path.unlink(missing_ok=True)
                    claimed = (
                        data.get("id")
                        if isinstance(data, dict) and isinstance(data.get("id"), str)
                        else "unknown"
                    )
                    _write_json_atomic(
                        response_path,
                        {"id": claimed, "error": str(exc)},
                        MAX_RESPONSE_BYTES,
                    )
                else:
                    try:
                        result = (
                            self._complete_request(data["request"])
                            if "request" in data and self._complete_request is not None
                            else self._complete(self._grant.model, messages)
                        )
                        _write_json_atomic(
                            response_path,
                            {"id": turn_id, "result": dict(result)},
                            MAX_RESPONSE_BYTES,
                        )
                    except Exception as exc:  # noqa: BLE001 - class only, never secrets
                        _write_json_atomic(
                            response_path,
                            {"id": turn_id, "error": type(exc).__name__},
                            MAX_RESPONSE_BYTES,
                        )
                return True
            time.sleep(POLL_SECONDS)
        return False

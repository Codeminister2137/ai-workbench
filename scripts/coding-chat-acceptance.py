"""Bounded, opt-in full-versus-reduced history comparison on synthetic code.

This is one paired fixture, not quality parity or delegation-economics evidence.
Default preparation is offline. --live permits at most two official-client calls;
failure stops the pair without retries or another billing source.
"""

from __future__ import annotations

import argparse
import builtins
import contextlib
import hashlib
import io
import json
import os
import queue
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, NamedTuple

from ai_agent import coding_chat_cli
from ai_agent import repo_coding_assistant as cli
from ai_agent.coding_chat import CodingChatController, CodingTurnResult
from ai_agent.tool_profiles import INSPECTION_PROFILE
from ai_provider.chat_transcripts import SQLiteChatTranscriptStore
from ai_provider.coding_sessions import CodingSession
from ai_provider.external_agents import ExternalAgentResult, run_external_agent

DRIVER_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


class LoggedConsole(io.TextIOBase):
    """Keep fixture evidence while displaying the actual owner's approval prompts."""

    def __init__(self, log, console):
        self.log, self.console = log, console

    def write(self, text):
        self.log.write(text)
        return self.console.write(text)

    def flush(self):
        for stream in (self.log, self.console):
            if not stream.closed:
                stream.flush()


SOURCE = "def window_end(start, size, total):\n    return min(total, start + size - 1)\n"
TESTS = """import unittest
from range_tools import window_end

class WindowTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(window_end(0, 0, 0), 0)
    def test_one(self):
        self.assertEqual(window_end(0, 1, 4), 1)
    def test_clamped(self):
        self.assertEqual(window_end(3, 5, 4), 4)
    def test_zero_size(self):
        self.assertEqual(window_end(2, 0, 4), 2)
    def test_negative_size(self):
        with self.assertRaises(ValueError):
            window_end(1, -1, 4)

if __name__ == '__main__':
    unittest.main()
"""
PROMPT = (
    "Correction: negative size must raise ValueError; zero size is valid. "
    "Fix window_end's exclusive end boundary in range_tools.py. Keep earlier "
    "owner decisions. Edit only range_tools.py using repo_shared tools. Do not "
    "run commands, delegate, use network/research or inspect outside this fixture. "
    "The host runs the unchanged tests; report what you changed and what you could not verify."
)
CATALOG = """[[models]]
route_id = "synthetic-codex-sol"
provider = "openai"
product = "codex"
model = "gpt-6.1-sol"
location = "external"
access_method = "codex_cli"
auth_method = "chatgpt_sign_in"
billing_source = "chatgpt_subscription_allowance"
cost_policy_tier = "allowances_allowed"
quality = "standard"
[models.capabilities]
chat = true
tools = true
"""


class ComparisonCase(NamedTuple):
    """Fixed synthetic inputs and a local reference used only by offline checks."""

    module: str
    source: str
    tests: str
    prompt: str
    earlier_decision: str
    reference: str


RESTRICTIONS = (
    "Keep earlier owner decisions. Edit only the named module using repo_shared tools. "
    "Do not run commands, delegate, use network/research or inspect outside this fixture. "
    "The host runs the unchanged tests; report what you changed and what you could not verify."
)
CASES = {
    "boundary": ComparisonCase(
        "range_tools.py",
        SOURCE,
        TESTS,
        PROMPT,
        "Owner decision: end is exclusive and capped at total. "
        "Initially clamp a negative size to zero.",
        "def window_end(start, size, total):\n"
        "    if size < 0:\n"
        '        raise ValueError("size must be non-negative")\n'
        "    return min(total, start + size)\n",
    ),
    "configuration": ComparisonCase(
        "settings.py",
        "def parse_delay(value):\n    return float(value)\n",
        """import unittest
from settings import parse_delay

class DelayTests(unittest.TestCase):
    def test_valid_boundaries(self):
        for value, expected in [('0', 0.0), (60, 60.0), ('2.5', 2.5)]:
            self.assertEqual(parse_delay(value), expected)
    def test_nonfinite(self):
        for value in ['nan', 'inf', '-inf', float('nan'), float('inf')]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_delay(value)
    def test_outside_range(self):
        for value in [-1, 60.01]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_delay(value)
    def test_malformed_or_boolean(self):
        for value in ['oops', '', None, True, False]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_delay(value)

if __name__ == '__main__':
    unittest.main()
""",
        "Correction: reject invalid delays with ValueError instead of clamping or defaulting. "
        "Fix parse_delay in settings.py. Accept finite numbers/numeric strings in [0, 60] "
        "inclusive, returning float. Reject booleans, None, malformed and nonfinite input. "
        + RESTRICTIONS,
        "Owner decision: parse_delay preserves its one-argument API and float result. "
        "Initially replace invalid delays with zero.",
        """import math

def parse_delay(value):
    if isinstance(value, bool):
        raise ValueError('delay must be numeric')
    try:
        delay = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('delay must be numeric') from exc
    if not math.isfinite(delay) or not 0 <= delay <= 60:
        raise ValueError('delay must be finite and in [0, 60]')
    return delay
""",
    ),
    "extraction": ComparisonCase(
        "invoice.py",
        """class Invoice:
    def __init__(self, subtotal, tax_rate):
        self.subtotal = subtotal
        self.tax_rate = tax_rate

    def total(self):
        return self.subtotal * 1.2
""",
        """import unittest
from unittest.mock import patch
import invoice

class InvoiceTests(unittest.TestCase):
    def test_object_rate(self):
        self.assertAlmostEqual(invoice.Invoice(100, 0.05).total(), 105)
    def test_zero_rate_and_subtotal(self):
        self.assertEqual(invoice.Invoice(100, 0).total(), 100)
        self.assertEqual(invoice.Invoice(0, 0.2).total(), 0)
    def test_reusable_function(self):
        self.assertAlmostEqual(invoice.total_with_tax(20, 0.1), 22)
    def test_method_delegates_current_values(self):
        item = invoice.Invoice(10, 0.2)
        item.tax_rate = 0.3
        with patch('invoice.total_with_tax', return_value=13) as calculation:
            self.assertEqual(item.total(), 13)
            calculation.assert_called_once_with(10, 0.3)

if __name__ == '__main__':
    unittest.main()
""",
        "Correction: use each Invoice object's current tax_rate; do not keep a fixed 20% rate. "
        "In invoice.py extract total_with_tax(subtotal, tax_rate), returning "
        "subtotal * (1 + tax_rate), and make Invoice.total delegate to that function. "
        "Preserve constructor/total signatures and support zero rate/subtotal. "
        "Do not add rounding, validation policy or new classes. " + RESTRICTIONS,
        "Owner decision: preserve the Invoice constructor and total method API. "
        "Initially calculate every invoice with a fixed 20% tax rate.",
        """def total_with_tax(subtotal, tax_rate):
    return subtotal * (1 + tax_rate)

class Invoice:
    def __init__(self, subtotal, tax_rate):
        self.subtotal = subtotal
        self.tax_rate = tax_rate

    def total(self):
        return total_with_tax(self.subtotal, self.tax_rate)
""",
    ),
    "authenticated_redirect": ComparisonCase(
        "provider_request.py",
        """from urllib.request import Request, urlopen

def submit(endpoint, token, payload):
    request = Request(endpoint, data=payload,
                      headers={'Authorization': 'Bearer ' + token}, method='POST')
    with urlopen(request, timeout=2) as response:
        return response.read()
""",
        """import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from provider_request import submit

class RedirectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.requests = []
        cls.redirect_status = 302
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                cls.requests.append((self.path, self.headers.get('Authorization'), body))
                self.send_response(cls.redirect_status if self.path == '/redirect' else 200)
                self.send_header('Location', '/destination')
                self.send_header('Content-Length', '0' if self.path == '/redirect' else '4')
                self.end_headers()
                if self.path != '/redirect':
                    self.wfile.write(b'done')
            def do_GET(self):
                cls.requests.append((self.path, self.headers.get('Authorization'), b''))
                self.send_response(200)
                self.send_header('Content-Length', '4')
                self.end_headers()
                self.wfile.write(b'done')
            def log_message(self, *args):
                pass
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.worker = threading.Thread(target=cls.server.serve_forever)
        cls.worker.start()
        cls.endpoint = 'http://127.0.0.1:' + str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(2)
    def setUp(self):
        self.requests.clear()
    def test_final_endpoint_preserves_bytes_and_credentials(self):
        self.assertEqual(submit(self.endpoint + '/source', 'synthetic-token', b'prompt'), b'done')
        self.assertEqual(self.requests, [('/source', 'Bearer synthetic-token', b'prompt')])
    def test_every_redirect_refuses_without_contacting_destination(self):
        for status in (301, 302, 303, 307, 308):
            with self.subTest(status=status):
                self.requests.clear()
                type(self).redirect_status = status
                with self.assertRaises(HTTPError) as raised:
                    submit(self.endpoint + '/redirect', 'synthetic-token', b'prompt')
                self.assertEqual(raised.exception.code, status)
                raised.exception.close()
                self.assertEqual(self.requests,
                                 [('/redirect', 'Bearer synthetic-token', b'prompt')])

if __name__ == '__main__':
    unittest.main()
""",
        "Review the authenticated request in provider_request.py, then fix submit to refuse "
        "all HTTP redirects before credentials or payload reach any redirect destination. "
        "Keep submit(endpoint, token, payload), POST bytes, two-second timeout and response "
        "bytes for a final endpoint. Propagate HTTPError for redirects. Use a standard-library "
        "HTTPRedirectHandler and opener; do not whitelist same-origin redirects. " + RESTRICTIONS,
        "Owner decision: provider requests must preserve credentials/payload at the original "
        "endpoint and reject every redirect, including same-origin redirects.",
        """from urllib.request import HTTPRedirectHandler, Request, build_opener

class RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def submit(endpoint, token, payload):
    request = Request(endpoint, data=payload,
                      headers={'Authorization': 'Bearer ' + token}, method='POST')
    with build_opener(RejectRedirect()).open(request, timeout=2) as response:
        return response.read()
""",
    ),
    "path_containment": ComparisonCase(
        "workspace_read.py",
        """from pathlib import Path

def read_project(root, name):
    root = Path(root).resolve()
    target = (root / name).absolute()
    if not str(target).startswith(str(root)):
        raise ValueError('outside workspace')
    return target.read_text(encoding='utf-8')
""",
        """import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from workspace_read import read_project

class ContainmentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.root = self.base / 'repo'
        self.outside = self.base / 'repo-extra'
        self.root.mkdir()
        self.outside.mkdir()
        (self.root / 'inside.txt').write_text('INSIDE_MARKER', encoding='utf-8')
        (self.outside / 'secret.txt').write_text('OUTSIDE_MARKER', encoding='utf-8')
    def tearDown(self):
        self.temporary.cleanup()
    def test_inside_relative_and_absolute_paths(self):
        for name in ('inside.txt', str(self.root / 'inside.txt')):
            with self.subTest(name=name):
                self.assertEqual(read_project(self.root, name), 'INSIDE_MARKER')
    def test_parent_traversal_is_refused(self):
        with self.assertRaises(ValueError):
            read_project(self.root, '../repo-extra/secret.txt')
    def test_absolute_prefix_cousin_is_refused(self):
        with self.assertRaises(ValueError):
            read_project(self.root, str(self.outside / 'secret.txt'))
    def test_directory_link_to_outside_is_refused(self):
        link = self.root / 'linked'
        if os.name == 'nt':
            subprocess.run(
                ['powershell', '-NoProfile', '-NonInteractive', '-Command',
                 'New-Item -ItemType Junction -Path $env:FIXTURE_LINK '
                 '-Target $env:FIXTURE_TARGET | Out-Null'],
                env={**os.environ, 'FIXTURE_LINK': str(link),
                     'FIXTURE_TARGET': str(self.outside)},
                check=True, capture_output=True, timeout=3,
            )
        else:
            link.symlink_to(self.outside, target_is_directory=True)
        try:
            with self.assertRaises(ValueError):
                read_project(self.root, 'linked/secret.txt')
            self.assertEqual((self.outside / 'secret.txt').read_text(), 'OUTSIDE_MARKER')
        finally:
            if os.name == 'nt':
                link.rmdir()
            else:
                link.unlink()

if __name__ == '__main__':
    unittest.main()
""",
        "Review workspace_read.py for traversal, path-prefix and directory-link escape. "
        "Fix read_project(root, name) to resolve paths and refuse every target outside the "
        "resolved root before reading its contents. Retain UTF-8 text and both relative "
        "and absolute inside-root paths. Raise ValueError for outside targets. Preserve "
        "ordinary file errors and permit resolved links that stay inside the root. "
        "Do not claim protection against concurrent hostile filesystem changes. " + RESTRICTIONS,
        "Owner decision: repository reads are contained by resolved path ancestry, "
        "rather than string prefix. Outside link targets must not be read.",
        """from pathlib import Path

def read_project(root, name):
    root = Path(root).resolve()
    target = (root / name).resolve()
    if not target.is_relative_to(root):
        raise ValueError('outside workspace')
    return target.read_text(encoding='utf-8')
""",
    ),
}


def prepare(
    workspace: Path, budget: int, case_name: str = "boundary", *, current_text: str | None = None
) -> tuple[str, int]:
    """Create equivalent fixtures and synthetic conversation history, without inference."""
    case = CASES[case_name]
    workspace.mkdir()
    (workspace / case.module).write_text(case.source, encoding="utf-8")
    (workspace / f"test_{case.module}").write_text(case.tests, encoding="utf-8")
    (workspace / "catalog.toml").write_text(CATALOG, encoding="utf-8")
    (workspace / "AGENTS.md").write_text(
        f"Synthetic fixture. Edit only {case.module}. Preserve tests and API. "
        "No new dependencies, delegation, external services, commands or outside files.\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "--quiet", str(workspace)], check=True)
    database = workspace / "session.sqlite3"
    session = CodingSession.open(
        database,
        "new",
        workspace,
        f"Synthetic {case_name} correction",
        [],
        privacy_class="public_or_low_risk",
        cost_policy="allowances_allowed",
    )
    store = SQLiteChatTranscriptStore(database)
    CodingChatController.create(
        store, session.session_id, workspace, "public_or_low_risk", "Synthetic comparison"
    )
    chat = CodingChatController(
        store, session.session_id, workspace, "public_or_low_risk", history_budget_chars=0
    )
    chat.turn(
        "Owner decision: standard library only; preserve API and tests. "
        "Do not add runtime dependencies or cloud-service calls to this code.",
        lambda request: CodingTurnResult(0, "Synthetic earlier model report. " * 400, "completed"),
    )
    chat.turn(
        case.earlier_decision,
        lambda request: CodingTurnResult(
            1,
            "Synthetic outdated proposed implementation. " * 200,
            "validation_failed",
            "fixture validation failed",
        ),
    )
    session.status("completed")
    chat.history_budget_chars = budget
    current_text = case.prompt if current_text is None else current_text
    return session.session_id, len(chat.history(current_text=current_text)) + len(current_text)


def comparison_command(command: tuple[str, ...]) -> list[str]:
    """Preserve grants and forward the fixture driver's explicit Python import path."""
    invocation = list(command)
    if invocation[invocation.index("--model") + 1] != "gpt-6.1-sol":
        raise ValueError("Comparison requires gpt-6.1-sol")
    for index, value in enumerate(invocation):
        if value.startswith("mcp_servers.repo_shared.env_vars="):
            forwarded = json.loads(value.split("=", 1)[1])
            if "PYTHONPATH" not in forwarded:
                forwarded.append("PYTHONPATH")
            invocation[index] = "mcp_servers.repo_shared.env_vars=" + json.dumps(forwarded)
    invocation[1:1] = ["--no-daemon", "-c", "model_reasoning_effort=medium"]
    invocation.insert(invocation.index("exec") + 1, "--ignore-user-config")
    return invocation


def permitted_client_operations(result: ExternalAgentResult, workspace: Path, module: str) -> bool:
    """Reject fixture-boundary violations even when the resulting code passes tests.

    Client events are supplemental evidence, not authorization or independent
    proof of effects. Missing/unparseable events cannot establish this check.
    """
    events = result.events
    if events is None or events.parse_errors:
        return False
    if events.command_events or events.web_search_events or events.file_change_events:
        return False
    allowed = {*INSPECTION_PROFILE.tool_names, "edit_file"}
    for event in events.tool_events:
        item = event.get("item", event)
        if not isinstance(item, dict):
            return False
        tool = item.get("tool", item.get("name"))
        if tool not in allowed:
            return False
        if tool == "edit_file":
            arguments = item.get("arguments")
            path = arguments.get("path") if isinstance(arguments, dict) else None
            if not isinstance(path, str):
                return False
            try:
                if (workspace / path).resolve() != (workspace / module).resolve():
                    return False
            except (OSError, ValueError):
                return False
    return True


def observed_shared_operations(
    workspace: Path, task_id: str, *, after_order: int = 0
) -> list[dict[str, Any]]:
    """Read existing host receipts for this invocation; never create or migrate storage."""
    prefix = f"shared:{task_id}:"
    with contextlib.closing(
        sqlite3.connect((workspace / "session.sqlite3").as_uri() + "?mode=ro", uri=True)
    ) as connection:
        rows = connection.execute(
            "SELECT rowid,operation,status FROM coding_receipts WHERE session_id=? AND rowid>? "
            "ORDER BY rowid",
            (task_id, after_order),
        ).fetchall()
    return [
        {
            "order": order,
            "run_id": operation.removeprefix(prefix).split(":", 2)[0],
            "operation": operation.removeprefix(prefix).split(":", 2)[1],
            "arguments_sha256": operation.removeprefix(prefix).split(":", 2)[2],
            "status": status,
        }
        for order, operation, status in rows
        if operation.startswith(prefix)
    ]


def observed_source_edits(
    operations: list[list[dict[str, Any]]],
    results: list[ExternalAgentResult],
    workspace: Path,
    module: str,
) -> bool:
    """Require source reads and ordered edits backed by matching host argument hashes."""
    edited = False
    for turn_operations, result in zip(operations, results, strict=True):
        source_calls: set[tuple[str, str]] = set()
        for event in result.events.tool_events if result.events else ():
            item = event.get("item", event)
            if not isinstance(item, dict):
                continue
            tool, arguments = item.get("tool", item.get("name")), item.get("arguments")
            if tool not in {"read_file", "edit_file"} or not isinstance(arguments, dict):
                continue
            path = arguments.get("path")
            if not isinstance(path, str):
                continue
            try:
                if (workspace / path).resolve() != (workspace / module).resolve():
                    continue
            except (OSError, ValueError):
                continue
            digest = hashlib.sha256(json.dumps(arguments, sort_keys=True).encode()).hexdigest()
            source_calls.add((tool, digest))
        read = False
        for operation in turn_operations:
            tool = operation["operation"]
            source_call = (tool, operation["arguments_sha256"]) in source_calls
            if tool == "edit_file" and not source_call:
                return False
            if operation["status"] != "completed" or not source_call:
                continue
            if tool == "read_file":
                read = True
            elif tool == "edit_file":
                if not read:
                    return False
                edited = True
    return edited


def fixture_snapshot(workspace: Path, module: str) -> dict[str, str]:
    """Fingerprint every non-source fixture path except the host's active SQLite files."""
    snapshot: dict[str, str] = {}
    host_files = {
        "session.sqlite3",
        "session.sqlite3-journal",
        "session.sqlite3-wal",
        "session.sqlite3-shm",
    }

    def visit(directory: Path) -> None:
        for path in directory.iterdir():
            name = path.relative_to(workspace).as_posix()
            if name in host_files or name == module:
                continue
            if path.is_symlink() or path.is_junction():
                snapshot[name] = "link:" + os.readlink(path)
            elif path.is_dir():
                snapshot[name] = "directory"
                visit(path)
            elif path.is_file():
                snapshot[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            else:
                snapshot[name] = "unsupported"

    visit(workspace)
    return snapshot


def effective_settings(command: Path) -> dict[str, object]:
    """Read effective settings through the installed client's local stdio API.

    No thread/start or turn/start request is sent. Config contents other than
    the selected model/reasoning are never persisted or printed.
    """
    process = subprocess.Popen(
        [
            str(command),
            "--no-daemon",
            "-c",
            "model=gpt-6.1-sol",
            "-c",
            "model_reasoning_effort=medium",
            "app-server",
            "--stdio",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    replies: queue.Queue[dict] = queue.Queue()

    def collect():
        assert process.stdout
        for line in process.stdout:
            try:
                reply = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(reply, dict):
                replies.put(reply)

    reader = threading.Thread(target=collect, name="codex-settings-reader")
    reader.start()
    deadline = time.monotonic() + 15

    def request(identifier, method, params):
        assert process.stdin
        process.stdin.write(
            json.dumps({"id": identifier, "method": method, "params": params}) + "\n"
        )
        process.stdin.flush()
        while True:
            reply = replies.get(timeout=max(0, deadline - time.monotonic()))
            if reply.get("id") == identifier:
                if "error" in reply:
                    raise ValueError("Client refused no-inference settings preflight")
                return reply["result"]

    try:
        client = request(
            1,
            "initialize",
            {
                "clientInfo": {"name": "synthetic-coding-acceptance", "version": "1"},
                "capabilities": {"experimentalApi": True},
            },
        )
        assert process.stdin
        process.stdin.write('{"method":"initialized"}\n')
        process.stdin.flush()
        config = request(2, "config/read", {"includeLayers": False})["config"]
        record = {
            "model": config.get("model"),
            "reasoning": config.get("model_reasoning_effort"),
            "client": client.get("userAgent"),
            "inference_requests": 0,
        }
        if record["model"] != "gpt-6.1-sol" or record["reasoning"] != "medium":
            raise ValueError("Installed client did not apply gpt-6.1-sol / medium")
        return record
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        reader.join(timeout=5)
        if process.stdin:
            process.stdin.close()
        if process.stdout:
            process.stdout.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--preflight", action="store_true", help="Verify effective settings without inference"
    )
    parser.add_argument("--codex-command", type=Path)
    parser.add_argument("--effective-settings", type=Path)
    parser.add_argument("--arm", choices=("full", "reduced", "both"), default="both")
    parser.add_argument("--case", choices=tuple(CASES), default="boundary")
    parser.add_argument(
        "--conversation",
        action="store_true",
        help="Discuss first, then submit the owner correction",
    )
    parser.add_argument(
        "--restart", action="store_true", help="Close and reopen the conversation after planning"
    )
    parser.add_argument(
        "--attended", action="store_true", help="Use real terminal steering and scoped approvals"
    )
    args = parser.parse_args()
    if args.attended and (args.conversation or args.arm == "both"):
        parser.error("--attended requires one arm and cannot use scripted --conversation input")
    if args.attended and args.live and not sys.stdin.isatty():
        parser.error("--attended --live requires the owner's controlling terminal")
    if args.restart and not args.conversation:
        parser.error("--restart requires --conversation")
    if args.conversation and args.arm == "both":
        parser.error("--conversation requires --arm full or reduced to preserve the two-call cap")
    if args.preflight:
        if args.live or not args.codex_command or not args.effective_settings:
            parser.error(
                "--preflight requires --codex-command and --effective-settings, without --live"
            )
        settings = effective_settings(args.codex_command.resolve())
        args.effective_settings.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        print(json.dumps(settings, indent=2))
        return 0
    if args.live:
        if not args.codex_command or not args.effective_settings:
            parser.error(
                "--live requires an installed client and a no-inference effective-settings receipt"
            )
        settings = json.loads(args.effective_settings.read_text(encoding="utf-8"))
        if settings.get("model") != "gpt-6.1-sol" or settings.get("reasoning") != "medium":
            parser.error("effective settings must verify gpt-6.1-sol / medium")
    artifact = Path(__file__).resolve().parents[1] / "artifacts" / "coding-chat-acceptance"
    artifact.mkdir(parents=True, exist_ok=True)
    # Outside the private repository: no ancestor repository instructions/source.
    fixture = Path(tempfile.mkdtemp(prefix="synthetic-coding-chat-"))
    artifact = artifact / fixture.name
    artifact.mkdir()
    arms: list[dict[str, object]] = []
    case = CASES[args.case]
    test_name = f"test_{case.module}"
    planning_prompt = (
        f"Read {case.module} using repo_shared and explain the defect and viable options. "
        "Keep earlier owner decisions and ask about material ambiguity. Do not edit any "
        "files or run commands, delegate, use network/research or inspect outside this fixture. "
        "Wait for the owner's follow-up before implementation."
    )
    owner_inputs = deque(["/exit"] if args.restart else [case.prompt, "/exit"])
    planning_unchanged = None
    planning_tools_read_only = None
    planning_source_read = None
    record: dict[str, object] = {
        "fixture": str(fixture),
        "live": args.live,
        "case": args.case,
        "conversation": args.conversation,
        "restart": args.restart,
        "attended": args.attended,
        "driver_sha256": DRIVER_SHA256,
        "model": "gpt-6.1-sol",
        "reasoning": "medium",
        "inputs_sha256": {
            name: hashlib.sha256(value.encode("utf-8")).hexdigest()
            for name, value in {
                "source": case.source,
                "tests": case.tests,
                "prompt": case.prompt,
                "earlier_decision": case.earlier_decision,
                **({"planning_prompt": planning_prompt} if args.conversation else {}),
            }.items()
        },
        "execution_module_sha256": hashlib.sha256(Path(cli.__file__).read_bytes()).hexdigest(),
        "arms": arms,
        "parity_established": False,
        "delegation_savings_established": False,
        "estimated_api_cost": None,
        "subscription_allowance_delta": None,
    }
    results = []
    host_operations: list[list[dict[str, Any]]] = []
    original_execute, original_input = cli._run_external_agent, builtins.input
    original_stdin = sys.stdin
    original_command = os.environ.get("CODEX_COMMAND")
    original_terminal_factory = coding_chat_cli.CodingChatInput
    controlled_terminals = []
    calls = 0

    def attended_terminal(*, stage):
        terminal = original_terminal_factory(stage=stage)
        controlled_terminals.append(terminal)
        return terminal

    def execute(prompt, config, **kwargs):
        nonlocal calls, planning_unchanged, planning_tools_read_only, planning_source_read
        if calls >= 2 or config.model != "gpt-6.1-sol":
            raise RuntimeError("Comparison call/model bound exceeded")
        calls += 1

        def runner(command, **options):
            return subprocess.run(comparison_command(command), **options)

        deadline = time.perf_counter() + 120
        if kwargs.get("deadline") is not None:
            deadline = min(deadline, kwargs["deadline"])
        name = config.cwd.name + (f".turn-{calls}" if args.conversation or args.attended else "")
        earlier_operations = observed_shared_operations(config.cwd, config.shared_task_id)
        after_order = max((int(item["order"]) for item in earlier_operations), default=0)
        try:
            result = run_external_agent(
                prompt, config, runner=runner, progress_callback=None, deadline=deadline
            )
        except BaseException as error:
            owner_inputs.clear()
            owner_inputs.append("/exit")
            if args.attended:
                for terminal in controlled_terminals:
                    terminal.close()
            if isinstance(error, subprocess.TimeoutExpired):
                for suffix, partial in (
                    ("events.jsonl", error.stdout),
                    ("stderr.log", error.stderr),
                ):
                    text = (
                        partial.decode("utf-8", errors="replace")
                        if isinstance(partial, bytes)
                        else partial or ""
                    )
                    (artifact / f"{name}.{suffix}").write_text(text, encoding="utf-8")
            raise
        results.append(result)
        host_operations.append(
            observed_shared_operations(config.cwd, config.shared_task_id, after_order=after_order)
        )
        if args.attended and result.returncode != 0:
            for terminal in controlled_terminals:
                terminal.close()
        (artifact / f"{name}.events.jsonl").write_text(result.stdout, encoding="utf-8")
        (artifact / f"{name}.stderr.log").write_text(result.stderr, encoding="utf-8")
        if args.conversation and calls == 1:
            events = result.events
            planning_tools_read_only = bool(
                events
                and not events.command_events
                and not events.file_change_events
                and not events.web_search_events
                and all(
                    event.get("item", {}).get("tool", event.get("name"))
                    in INSPECTION_PROFILE.tool_names
                    for event in events.tool_events
                )
            )
            planning_source_read = bool(
                events
                and any(
                    event.get("type") == "item.completed"
                    and event.get("item", {}).get("tool") == "read_file"
                    and isinstance(event["item"].get("arguments", {}).get("path"), str)
                    and (config.cwd / event["item"]["arguments"]["path"]).resolve()
                    == (config.cwd / case.module).resolve()
                    and event["item"].get("status") == "completed"
                    and not event["item"].get("error")
                    and not (event["item"].get("result") or {}).get("isError")
                    for event in events.tool_events
                )
            )
            planning_unchanged = (
                (config.cwd / case.module).is_file()
                and not (config.cwd / case.module).is_symlink()
                and (config.cwd / case.module).read_text(encoding="utf-8") == case.source
                and all(
                    (config.cwd / filename).is_file()
                    and not (config.cwd / filename).is_symlink()
                    and (config.cwd / filename).read_bytes() == contents
                    for filename, contents in protected.items()
                )
                and fixture_snapshot(config.cwd, case.module) == paths_before
            )
            if (
                not planning_unchanged
                or not planning_tools_read_only
                or not planning_source_read
                or result.returncode != 0
                or (result.events and result.events.failure_reason)
            ):
                owner_inputs.clear()
                owner_inputs.append("/exit")
        return result

    try:
        if args.live:
            os.environ["CODEX_COMMAND"] = str(args.codex_command.resolve())
            cli._run_external_agent = execute
            if args.attended:
                coding_chat_cli.CodingChatInput = attended_terminal
            if not args.attended:
                builtins.input = (
                    (lambda prompt: owner_inputs.popleft())
                    if args.conversation
                    else lambda prompt: "/exit"
                )
                sys.stdin = io.StringIO("/exit\n")
        for name, budget in (("full", 0), ("reduced", 4000)):
            if args.arm != "both" and args.arm != name:
                continue
            workspace = fixture / name
            session_id, context_chars = prepare(
                workspace,
                budget,
                args.case,
                current_text=planning_prompt if args.conversation else None,
            )
            baseline = subprocess.run(
                [sys.executable, test_name],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert baseline.returncode != 0, "Fixture must expose the original bug"
            arm = {"name": name, "context_chars": context_chars, "baseline_tests_passed": False}
            arms.append(arm)
            (artifact / f"{name}.before.py").write_text(case.source, encoding="utf-8")
            if not args.live:
                continue
            protected = {
                filename: (workspace / filename).read_bytes()
                for filename in (test_name, "AGENTS.md", "catalog.toml")
            }
            paths_before = fixture_snapshot(workspace, case.module)
            log = io.StringIO()
            result_start = len(results)
            started = time.monotonic()
            if args.attended:
                print(
                    "Attended synthetic fixture, two turns maximum. PHASE 1: wait for the "
                    "first edit ticket. BEFORE approving it, enter /steer Add a comment "
                    "explaining the negative-size check; preserve behavior. Then enter "
                    "/approve stale-ticket yes to test refusal, and approve using the "
                    "actual fresh ticket. PHASE 2: the queued follow-up requests another "
                    "edit; deny it with /approve NEW_TICKET_ID no. A first-turn summary "
                    "does not finish this check. If You> appears without a second turn, "
                    "enter Add a comment explaining the negative-size check; preserve "
                    "behavior. After the second turn's report, enter /exit. Do not submit "
                    "a third request. Enter synthetic fixture text only."
                )
            with contextlib.redirect_stdout(
                LoggedConsole(log, sys.stdout) if args.attended else log
            ):
                invocation = [
                    "--mode",
                    "coding-chat",
                    "--execute",
                    "--repo-root",
                    str(workspace),
                    "--catalog",
                    str(workspace / "catalog.toml"),
                    "--route-id",
                    "synthetic-codex-sol",
                    "--privacy",
                    "public_or_low_risk",
                    "--cost-policy",
                    "allowances_allowed",
                    "--approval-policy",
                    "interactive" if args.attended else "workspace_write",
                    "--skip-prompt-review",
                    "--coding-session",
                    session_id,
                    "--coding-session-db",
                    str(workspace / "session.sqlite3"),
                    "--coding-chat-history-budget-chars",
                    str(budget),
                    "--timeout-seconds",
                    "120",
                    planning_prompt if args.conversation else case.prompt,
                ]
                statuses = [cli.main(invocation)]
                if (
                    args.restart
                    and statuses[0] == 0
                    and planning_unchanged is True
                    and planning_tools_read_only is True
                    and planning_source_read is True
                    and len(results) - result_start == 1
                ):
                    owner_inputs.clear()
                    owner_inputs.append("/exit")
                    invocation[-1] = case.prompt
                    statuses.append(cli.main(invocation))
                status = next((value for value in statuses if value != 0), 0)
            arm.update(status=status, elapsed_seconds=time.monotonic() - started)
            arm["cli_invocations"] = len(statuses)
            if args.attended:
                arm["attended_arbitration_verified"] = False
            (artifact / f"{name}.log").write_text(log.getvalue(), encoding="utf-8")
            unchanged = (
                (workspace / test_name).is_file()
                and (not (workspace / test_name).is_symlink())
                and (workspace / test_name).read_bytes() == protected[test_name]
            )
            protected_unchanged = all(
                (workspace / filename).is_file()
                and not (workspace / filename).is_symlink()
                and (workspace / filename).read_bytes() == contents
                for filename, contents in protected.items()
            )
            source_present = (workspace / case.module).is_file()
            source_regular = source_present and not (workspace / case.module).is_symlink()
            fixture_paths_unchanged = fixture_snapshot(workspace, case.module) == paths_before
            after = (workspace / case.module).read_text(encoding="utf-8") if source_regular else ""
            (artifact / f"{name}.after.py").write_text(after, encoding="utf-8")
            validation = (
                subprocess.run(
                    [sys.executable, test_name],
                    cwd=workspace,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if unchanged and protected_unchanged and fixture_paths_unchanged and source_regular
                else None
            )
            host_tests_passed = validation is not None and validation.returncode == 0
            arm_results = results[result_start:]
            arm_operations = host_operations[result_start:]
            client_operations_permitted = bool(arm_results) and all(
                permitted_client_operations(result, workspace, case.module)
                for result in arm_results
            )
            allowed = {*INSPECTION_PROFILE.tool_names, "edit_file"}
            host_operations_permitted = bool(arm_operations) and all(
                operation["operation"] in allowed
                for operations in arm_operations
                for operation in operations
            )
            host_read_then_edit = observed_source_edits(
                arm_operations,
                arm_results,
                workspace,
                case.module,
            )
            passed = (
                host_tests_passed
                and client_operations_permitted
                and host_operations_permitted
                and host_read_then_edit
            )
            if args.conversation or args.attended:
                if args.conversation:
                    passed = (
                        passed
                        and planning_unchanged is True
                        and planning_tools_read_only is True
                        and planning_source_read is True
                        and len(results) - result_start == 2
                    )
                arm["planning_files_unchanged"] = planning_unchanged
                arm["planning_tools_read_only"] = planning_tools_read_only
                arm["planning_source_read"] = planning_source_read
                arm["turns"] = [
                    {
                        "returncode": turn.returncode,
                        "usage": turn.events.usage if turn.events else None,
                        "failure_reason": turn.events.failure_reason if turn.events else None,
                    }
                    for turn in results[result_start:]
                ]
            arm.update(
                tests_unchanged=unchanged,
                protected_files_unchanged=protected_unchanged,
                source_present=source_present,
                source_regular=source_regular,
                fixture_paths_unchanged=fixture_paths_unchanged,
                host_tests_passed=host_tests_passed,
                client_operations_permitted=client_operations_permitted,
                host_operations=arm_operations,
                host_operations_permitted=host_operations_permitted,
                host_read_then_edit=host_read_then_edit,
                tests_passed=passed,
            )
            if validation:
                (artifact / f"{name}.validation.log").write_text(
                    validation.stdout + validation.stderr, encoding="utf-8"
                )
            if results:
                last = results[-1]
                arm.update(
                    usage=last.events.usage if last.events else None,
                    usage_scope="last_turn" if args.conversation or args.attended else "entire_arm",
                    failure_reason=last.events.failure_reason if last.events else None,
                    command_events=len(last.events.command_events) if last.events else None,
                    tool_events=len(last.events.tool_events) if last.events else None,
                )
                (artifact / f"{name}.events.jsonl").write_text(last.stdout, encoding="utf-8")
                (artifact / f"{name}.stderr.log").write_text(last.stderr, encoding="utf-8")
            if status != 0 or not unchanged or not protected_unchanged or not passed:
                record["stopped_after_failure"] = True
                break
    finally:
        cli._run_external_agent, builtins.input = original_execute, original_input
        coding_chat_cli.CodingChatInput = original_terminal_factory
        sys.stdin = original_stdin
        if original_command is None:
            os.environ.pop("CODEX_COMMAND", None)
        else:
            os.environ["CODEX_COMMAND"] = original_command
        record["live_calls"] = calls
        (artifact / "results.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record, indent=2))
    return (
        1
        if args.live
        and any(
            a.get("status") != 0 or not a.get("tests_passed") or not a.get("tests_unchanged")
            for a in arms
        )
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())

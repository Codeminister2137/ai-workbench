"""One serial chunked-request diagnostic; metadata only, never payload/header values.

Run from the repository root under a 45-second external timeout. Instrumentation
changes timing, so a passing observation cannot explain a historical abort.
"""

import datetime
import http.client
import http.server
import json
import socket
import socketserver
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

OUT = Path(".tmp/socket-framing-442f286a")
OUT.mkdir(parents=True, exist_ok=False)
events = []
lock = threading.Lock()


def record(event, **fields):
    with lock:
        events.append(
            dict(
                utc=datetime.datetime.now(datetime.UTC).isoformat(),
                ns=time.perf_counter_ns(),
                thread=threading.get_ident(),
                event=event,
                **fields,
            )
        )


def observe(owner, name, metadata=lambda *a, **k: {}):
    original = getattr(owner, name)

    def wrapped(*args, **kwargs):
        fields = metadata(*args, **kwargs)
        record(name + ".start", **fields)
        try:
            result = original(*args, **kwargs)
        except BaseException as error:
            record(
                name + ".error",
                **fields,
                error=type(error).__name__,
                errno=getattr(error, "errno", None),
                winerror=getattr(error, "winerror", None),
            )
            raise
        record(name + ".end", **fields, **({"bytes": result} if name == "readinto" else {}))
        return result

    return patch.object(owner, name, wrapped)


def rejection(handler, code, *args, **kwargs):
    lengths = handler.headers.get_all("Content-Length", [])
    return dict(
        connection=id(handler.connection),
        status=int(code),
        content_length_count=len(lengths),
        content_length=int(lengths[0]) if len(lengths) == 1 and lengths[0].isdigit() else None,
        transfer_encoding_present=bool(handler.headers.get("Transfer-Encoding")),
    )


def send(connection, data):
    return dict(
        connection=id(connection), bytes=len(data) if isinstance(data, (bytes, str)) else None
    )


code = 2
try:
    with (
        observe(http.client.HTTPConnection, "send", send),
        observe(http.client.HTTPResponse, "begin"),
        observe(http.server.BaseHTTPRequestHandler, "send_response", rejection),
        observe(http.server.BaseHTTPRequestHandler, "end_headers"),
        observe(socket.SocketIO, "readinto"),
        observe(socketserver.StreamRequestHandler, "finish"),
        observe(socketserver.TCPServer, "shutdown_request"),
        observe(socketserver.TCPServer, "close_request"),
    ):
        code = pytest.main(
            [
                "-q",
                "-p",
                "no:xdist",
                "apps/workbench_dashboard/tests/test_inference_proxy.py::test_run_scope_auth_revocation_and_size",
                "--junitxml=" + str(OUT / "result.xml"),
            ]
        )
finally:
    (OUT / "events.json").write_text(json.dumps(events, indent=2), encoding="utf-8")
    (OUT / "receipt.json").write_text(
        json.dumps(
            {
                "exit_code": int(code),
                "python": sys.version,
                "events": len(events),
                "bounds": "one test, serial, one invocation; external timeout 45s",
                "limitation": "application observations, no packet/ETW trace; timing perturbed",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
sys.exit(code)

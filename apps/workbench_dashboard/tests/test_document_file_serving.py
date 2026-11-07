"""Document file serving: active content neutralized, bytes intact."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
from dashboard_web_app import DashboardRequestHandler


@pytest.fixture
def doc_server(tmp_path):
    config_path = tmp_path / "dashboard.json"
    config_path.write_text(
        json.dumps({"provider": "ollama", "model": "fake", "title": "Test Board"}),
        encoding="utf-8",
    )
    library = tmp_path / "docs" / "library"
    library.mkdir(parents=True)
    (library / "evil.html").write_text("<script>fetch('/api/inbox')</script>", encoding="utf-8")
    (library / "pic.svg").write_text("<svg>not-an-image</svg>", encoding="utf-8")
    (library / "note.pdf").write_bytes(b"%PDF-1.4 fake")

    class TestHandler(DashboardRequestHandler):
        def log_message(self, format, *args):
            return

    TestHandler.config_path = config_path
    TestHandler.data_dir = tmp_path / "data"
    TestHandler.repo_root = tmp_path
    server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def _get(base: str, path: str):
    with urllib.request.urlopen(base + path, timeout=10) as response:
        return response.status, dict(response.headers), response.read()


def test_html_served_as_inert_text(doc_server) -> None:
    status, headers, body = _get(doc_server, "/api/documents/library/evil.html/file")
    assert status == 200
    assert headers["Content-Type"] == "text/plain"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert b"<script>" in body


def test_svg_served_as_inert_text(doc_server) -> None:
    status, headers, _body = _get(doc_server, "/api/documents/library/pic.svg/file")
    assert status == 200
    assert headers["Content-Type"] == "text/plain"
    assert headers["X-Content-Type-Options"] == "nosniff"


def test_pdf_keeps_type_and_gains_nosniff(doc_server) -> None:
    status, headers, body = _get(doc_server, "/api/documents/library/note.pdf/file")
    assert status == 200
    assert headers["Content-Type"] == "application/pdf"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert body == b"%PDF-1.4 fake"


def test_unknown_document_stays_404(doc_server) -> None:
    try:
        _get(doc_server, "/api/documents/library/missing/file")
    except urllib.error.HTTPError as exc:
        assert exc.code == 404
    else:  # pragma: no cover - fail loudly, never pass silently
        raise AssertionError("expected HTTP 404")

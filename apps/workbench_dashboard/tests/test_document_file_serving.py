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
    (library / "polish.md").write_text(
        "# Zażółć gęślą jaźń\n\nBielsko-Biała — “źródło”.\n", encoding="utf-8", newline="\n"
    )

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


def test_document_pins_round_trip_and_sort_first(doc_server) -> None:
    from dashboard_test_http import get_json, post_json

    before = get_json(doc_server, "/api/documents")["documents"]
    assert all(not doc.get("pinned") for doc in before)
    target = next(doc for doc in before if doc["id"].endswith("note.pdf"))["id"]
    updated = post_json(doc_server, "/api/documents/pins", {"id": target, "pinned": True})
    assert updated["ok"] is True
    after = get_json(doc_server, "/api/documents")["documents"]
    assert after[0]["id"] == target
    assert after[0]["pinned"] is True
    post_json(doc_server, "/api/documents/pins", {"id": target, "pinned": False})
    reread = get_json(doc_server, "/api/documents")["documents"]
    assert all(not doc.get("pinned") for doc in reread)
    with pytest.raises(urllib.error.HTTPError) as exc:
        post_json(doc_server, "/api/documents/pins", {"id": "", "pinned": True})
    assert exc.value.code == 400


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


def test_markdown_download_and_preview_preserve_polish(doc_server) -> None:
    from dashboard_test_http import get_json

    expected = "# Zażółć gęślą jaźń\n\nBielsko-Biała — “źródło”.\n"
    with urllib.request.urlopen(
        doc_server + "/api/documents/library/polish.md/file", timeout=10
    ) as response:
        assert response.headers.get_content_type() == "text/markdown"
        assert response.headers.get_content_charset() == "utf-8"
        assert response.read() == expected.encode("utf-8")
    preview = get_json(doc_server, "/api/documents/library/polish.md?content=1")
    assert preview["content"] == expected

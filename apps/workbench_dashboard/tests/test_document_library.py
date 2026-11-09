"""Document library scan, front-matter, and path-jail tests."""

from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer
from urllib.request import urlopen

import pytest
from dashboard_web_app import DashboardRequestHandler
from document_library import DocumentLibrary, parse_front_matter


@pytest.fixture
def library_roots(tmp_path):
    public = tmp_path / "repo" / "docs" / "library"
    private = tmp_path / "repo" / "docs" / "library-private"
    public.mkdir(parents=True)
    private.mkdir(parents=True)
    (public / "hello.md").write_text(
        "---\ntitle: Hello\ntags: [a, b]\nproject: demo\n---\nBody here.\n",
        encoding="utf-8",
    )
    (public / "plain.md").write_text("No front matter.\n", encoding="utf-8")
    (public / "deck.pdf").write_bytes(b"%PDF-fake")
    (private / "prices.md").write_text("---\ntitle: Prices\n---\nSecret.\n", encoding="utf-8")
    return tmp_path / "repo"


def test_lists_all_roots_newest_first(library_roots) -> None:
    docs = DocumentLibrary(library_roots).list_documents()
    by_id = {doc["id"]: doc for doc in docs}
    assert set(by_id) == {
        "library/hello.md",
        "library/plain.md",
        "library/deck.pdf",
        "private/prices.md",
    }
    assert by_id["library/hello.md"]["title"] == "Hello"
    assert by_id["library/hello.md"]["tags"] == ["a", "b"]
    assert by_id["library/hello.md"]["project"] == "demo"
    assert by_id["library/hello.md"]["sensitivity"] == "public"
    assert by_id["library/hello.md"]["renderable"] is True
    assert by_id["library/deck.pdf"]["renderable"] is False
    assert by_id["private/prices.md"]["sensitivity"] == "private"
    assert by_id["library/plain.md"]["title"] == "plain"


def test_archived_flag_flows_to_entries(library_roots) -> None:
    """Front-matter archived:true marks archive-tab documents."""
    public = library_roots / "docs" / "library"
    (public / "old.md").write_text(
        "---\ntitle: Old\narchived: true\n---\nStale.\n", encoding="utf-8"
    )
    docs = DocumentLibrary(library_roots).list_documents()
    by_id = {doc["id"]: doc for doc in docs}
    assert by_id["library/old.md"]["archived"] is True
    assert by_id["library/hello.md"]["archived"] is False
    assert by_id["library/plain.md"]["archived"] is False


def test_missing_roots_scan_empty(tmp_path) -> None:
    assert DocumentLibrary(tmp_path / "empty").list_documents() == []


def test_front_matter_without_block() -> None:
    fields, body = parse_front_matter("Just text.\n")
    assert (fields, body) == ({}, "Just text.\n")


def test_get_refuses_traversal(library_roots) -> None:
    library = DocumentLibrary(library_roots)
    with pytest.raises(ValueError):
        library.get("library/../secret.md")
    with pytest.raises(ValueError):
        library.get("library/..\\secret.md")
    with pytest.raises(KeyError):
        library.get("nope/file.md")
    with pytest.raises(KeyError):
        library.get("library/missing.md")


def test_read_text_strips_front_matter(library_roots) -> None:
    body, truncated = DocumentLibrary(library_roots).read_text("library/hello.md")
    assert body == "Body here.\n"
    assert truncated is False


def test_read_text_refuses_binary(library_roots) -> None:
    with pytest.raises(ValueError):
        DocumentLibrary(library_roots).read_text("library/deck.pdf")


def test_read_bytes_reports_pdf_type(library_roots) -> None:
    data, content_type = DocumentLibrary(library_roots).read_bytes("library/deck.pdf")
    assert data == b"%PDF-fake"
    assert content_type == "application/pdf"


def test_hidden_files_are_skipped(library_roots) -> None:
    hidden = library_roots / "docs" / "library" / ".hidden.md"
    hidden.write_text("x", encoding="utf-8")
    docs = DocumentLibrary(library_roots).list_documents()
    assert "library/.hidden.md" not in {doc["id"] for doc in docs}
    with pytest.raises(KeyError):
        DocumentLibrary(library_roots).get("library/.hidden.md")


@pytest.fixture
def docs_server(tmp_path, library_roots):
    data_dir = tmp_path / "data"

    class TestHandler(DashboardRequestHandler):
        def log_message(self, format, *args):
            return

    TestHandler.config_path = tmp_path / "dashboard.json"
    TestHandler.config_path.write_text("{}", encoding="utf-8")
    TestHandler.data_dir = data_dir
    TestHandler.repo_root = library_roots
    server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def test_documents_api_lists_and_serves(docs_server) -> None:
    import json

    with urlopen(f"{docs_server}/api/documents", timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))
    assert payload["ok"] is True
    assert len(payload["documents"]) == 4
    with urlopen(f"{docs_server}/api/documents/library/hello.md", timeout=5) as response:
        detail = json.loads(response.read().decode("utf-8"))
    assert detail["ok"] is True
    assert detail["entry"]["title"] == "Hello"
    with urlopen(f"{docs_server}/api/documents/library/hello.md?content=1", timeout=5) as response:
        content = json.loads(response.read().decode("utf-8"))
    assert content["content"] == "Body here.\n"


def test_document_file_serves_bytes(docs_server) -> None:
    with urlopen(f"{docs_server}/api/documents/library/deck.pdf/file", timeout=5) as response:
        assert response.headers.get_content_type() == "application/pdf"
        assert response.read() == b"%PDF-fake"


def test_document_unknown_is_404(docs_server) -> None:
    from urllib.error import HTTPError

    try:
        urlopen(f"{docs_server}/api/documents/library/missing.md", timeout=5)
        raise AssertionError("expected 404")
    except HTTPError as exc:
        assert exc.code == 404

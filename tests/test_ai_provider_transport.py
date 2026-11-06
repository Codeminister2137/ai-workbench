"""Provider credentials and prompts must never follow HTTP redirects."""

import io
import threading
from http.client import HTTPMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast
from urllib.error import HTTPError
from urllib.request import Request

import pytest
from ai_provider.errors import ProviderErrorCategory
from ai_provider.http_transport import MAX_RESPONSE_BYTES, iter_response_lines, urlopen


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_redirect_does_not_contact_destination(status, method):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else b""
            requests.append((self.path, self.headers.get("Authorization"), body))
            self.send_response(status if self.path == "/source" else 200)
            port = cast(ThreadingHTTPServer, self.server).server_port
            self.send_header("Location", f"http://localhost:{port}/destination")
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_POST = do_GET

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        request = Request(
            f"http://127.0.0.1:{server.server_port}/source",
            data=b"private synthetic prompt" if method == "POST" else None,
            headers={"Authorization": "Bearer synthetic-token"},
            method=method,
        )
        with pytest.raises(HTTPError) as error:
            urlopen(request, timeout=2)
        assert error.value.code == status
        error.value.close()
        expected_body = b"private synthetic prompt" if method == "POST" else b""
        assert requests == [("/source", "Bearer synthetic-token", expected_body)]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(2)


def test_https_downgrade_is_refused_before_following():
    from ai_provider.http_transport import _RejectRedirect

    request = Request("https://provider.invalid", headers={"Authorization": "Bearer synthetic"})
    assert (
        _RejectRedirect().redirect_request(
            request, io.BytesIO(), 302, "Found", HTTPMessage(), "http://other.invalid"
        )
        is None
    )


class _FakeResponse:
    """Minimal fake response supporting .read(size) chunked reads."""

    def __init__(self, data: bytes, chunk_size: int | None = None):
        self._data = data
        self._pos = 0
        self._chunk_size = chunk_size
        self.headers: dict[str, str] = {}

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            result = self._data[self._pos :]
            self._pos = len(self._data)
            return result
        result = self._data[self._pos : self._pos + size]
        self._pos += len(result)
        return result

    def getheader(self, name, default=None):
        return self.headers.get(name, default)


class _NoSizeArgResponse:
    """Legacy stub whose read() takes no size arg."""

    def __init__(self, lines):
        self._lines = lines
        self.headers: dict[str, str] = {}

    def read(self):
        raise TypeError("read() takes no size arg")

    def __iter__(self):
        return iter(self._lines)

    def getheader(self, name, default=None):
        return self.headers.get(name, default)


def test_iter_response_lines_single_giant_line_raises():
    # Fake response whose read() returns one 3MB line
    big_line = b"x" * (3 * 1024 * 1024)  # 3 MiB, exceeds default 2 MiB bound
    resp = _FakeResponse(big_line)
    with pytest.raises(Exception) as exc:
        list(iter_response_lines(resp))
    err = exc.value
    assert err.category == ProviderErrorCategory.NON_RETRYABLE


def test_iter_response_lines_normal_multi_line_stream_identically():
    body = b"hello\nworld\nfoo bar\n"
    resp = _FakeResponse(body)
    assert b"".join(iter_response_lines(resp)) == body
    # Also verify line splitting
    resp2 = _FakeResponse(body)
    assert list(iter_response_lines(resp2)) == [b"hello\n", b"world\n", b"foo bar\n"]


def test_iter_response_lines_cumulative_overflow_still_raises():
    # Many small lines that cumulatively exceed bound
    limit = 100
    line = b"a" * 10 + b"\n"  # 11 bytes each
    body = line * 10  # 110 bytes > 100
    resp = _FakeResponse(body)
    with pytest.raises(Exception) as exc:
        list(iter_response_lines(resp, limit=limit))
    err = exc.value
    assert err.category == ProviderErrorCategory.NON_RETRYABLE


def test_iter_response_lines_empty_yields_nothing():
    resp = _FakeResponse(b"")
    assert list(iter_response_lines(resp)) == []


def test_iter_response_lines_trailing_partial_line():
    body = b"hello\nworld"  # no trailing newline
    resp = _FakeResponse(body)
    assert list(iter_response_lines(resp)) == [b"hello\n", b"world"]


def test_iter_response_lines_single_line_overflow_without_newline():
    # Giant line without newline should also raise single-line breach
    big_line = b"y" * (MAX_RESPONSE_BYTES + 1)
    resp = _FakeResponse(big_line)
    with pytest.raises(Exception) as exc:
        list(iter_response_lines(resp))
    assert exc.value.category == ProviderErrorCategory.NON_RETRYABLE


def test_iter_response_lines_legacy_path_cannot_bound_single_lines():
    # Legacy path should still enforce cumulative bound
    limit = 50
    lines = [b"a" * 20 + b"\n", b"b" * 20 + b"\n", b"c" * 20 + b"\n"]  # 63 cumulative > 50
    resp = _NoSizeArgResponse(lines)
    with pytest.raises(Exception) as exc:
        list(iter_response_lines(resp, limit=limit))
    assert exc.value.category == ProviderErrorCategory.NON_RETRYABLE

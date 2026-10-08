"""Provider credentials and prompts must never follow HTTP redirects."""

import io
import threading
from http.client import HTTPMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast
from urllib.error import HTTPError
from urllib.request import Request

import pytest
from ai_provider.http_transport import urlopen


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

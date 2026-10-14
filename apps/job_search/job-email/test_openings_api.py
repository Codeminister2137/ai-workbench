"""API wire contracts and refusal boundaries; no external service or model calls."""

import io
import json
import socket
import threading
import time
from types import SimpleNamespace

import pytest
from openings_api import MAX_BODY_BYTES, OpeningsAPI, OpeningsAPIError, OpeningsPosting


def posting():
    return OpeningsPosting(
        title="Python Developer",
        company="Synthetic",
        source="test_source",
        external_id="req-7",
        job_url="https://example.invalid/jobs/7",
        description="Synthetic vacancy only",
        is_remote=True,
    )


@pytest.fixture
def wire(monkeypatch):
    state = SimpleNamespace(
        status=201,
        content_type="application/json",
        calls=[],
        closed=0,
        body=json.dumps(
            {"success": True, "affected_count": 1, "job_ids": ["canonical-7"], "message": "created"}
        ).encode(),
    )

    class Connection:
        def __init__(self, host, port, timeout):
            self.sock = SimpleNamespace(
                settimeout=lambda seconds: None, shutdown=lambda how: None, fileno=lambda: 1
            )
            state.endpoint = (host, port, timeout)

        def connect(self):
            pass

        def request(self, method, path, body, headers):
            state.calls.append((method, path, body, headers))

        def getresponse(self):
            body = io.BytesIO(state.body)
            return SimpleNamespace(
                status=state.status,
                getheader=lambda name, default: state.content_type,
                read1=body.read1,
                close=body.close,
            )

        def close(self):
            state.closed += 1

    monkeypatch.setattr("openings_api.http.client.HTTPConnection", Connection)
    return state


def client(**kwargs):
    return OpeningsAPI(host="127.0.0.1", port=8000, token="synthetic-token", **kwargs)


def test_intake_explicitly_new_and_only_posting_data(wire):
    assert client(mirror_fix_verified=True).add_posting(posting()) == "canonical-7"
    method, path, body, headers = wire.calls[0]
    assert (method, path) == ("POST", "/api/jobs")
    assert json.loads(body) == posting().payload()
    assert json.loads(body)["status"] == "new"
    assert headers["X-Openings-Token"] == "synthetic-token"
    assert wire.closed == 1 and len(wire.calls) == 1


def test_writes_require_operator_verification_before_io(wire):
    with pytest.raises(OpeningsAPIError, match="mirror fix"):
        client().add_posting(posting())
    assert wire.calls == []


def test_export_one_page_keeps_tracking_as_metadata(wire):
    wire.status = 200
    wire.body = json.dumps(
        [
            {
                "job_id": "canonical-7",
                "title": "Python Developer",
                "company": "Synthetic",
                "status": "applied",
            }
        ]
    ).encode()
    (vacancy,) = client().export_jobs(limit=1, offset=7)
    assert vacancy.id == "openings:canonical-7"
    assert vacancy.contact_email is None
    assert json.loads(vacancy.raw_content)["status"] == "applied"
    assert wire.calls[0][:2] == ("GET", "/api/export/jobs?format=json&limit=1&offset=7")
    assert len(wire.calls) == 1


def test_export_accepts_case_insensitive_json_media_type(wire):
    wire.status = 200
    wire.content_type = "Application/JSON; Charset=UTF-8"
    wire.body = json.dumps(
        [{"job_id": "canonical-7", "title": "Python Developer", "company": "Synthetic"}]
    ).encode()

    (vacancy,) = client().export_jobs(limit=1)

    assert vacancy.id == "openings:canonical-7"
    assert wire.calls[0][:2] == ("GET", "/api/export/jobs?format=json&limit=1&offset=0")
    assert len(wire.calls) == 1 and wire.closed == 1


@pytest.mark.parametrize("status", [301, 302, 307, 401, 409, 500])
def test_http_failures_never_redirect_retry_or_disclose_body(wire, status):
    wire.status, wire.body = status, b"private synthetic server detail"
    with pytest.raises(OpeningsAPIError) as error:
        client(mirror_fix_verified=True).add_posting(posting())
    assert "private" not in str(error.value) and "synthetic-token" not in str(error.value)
    assert len(wire.calls) == 1 and wire.closed == 1


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"[]",
        b'{"success":false}',
        b'{"success":true,"affected_count":true,"job_ids":["x"],"message":"created"}',
    ],
)
def test_malformed_intake_is_not_success(wire, body):
    wire.body = body
    with pytest.raises(OpeningsAPIError):
        client(mirror_fix_verified=True).add_posting(posting())
    assert wire.closed == 1


def test_response_size_bound(wire):
    wire.status = 200
    wire.body = b" " * (MAX_BODY_BYTES + 1)
    with pytest.raises(OpeningsAPIError, match="body bound"):
        client().export_jobs()
    assert wire.closed == 1


def test_request_size_bound_prevents_io(wire):
    large = OpeningsPosting(
        "t", "c", "s", "id", "https://example.invalid", description="x" * MAX_BODY_BYTES
    )
    with pytest.raises(ValueError, match="body bound"):
        client(mirror_fix_verified=True).add_posting(large)
    assert wire.calls == []


@pytest.mark.parametrize("host", ["example.com", "localhost", "192.168.1.1", "0.0.0.0"])
def test_non_numeric_or_non_loopback_hosts_rejected(host):
    with pytest.raises(ValueError):
        OpeningsAPI(host=host, port=8000, token="synthetic-token")


@pytest.mark.parametrize("kwargs", [{"limit": 0}, {"limit": 1001}, {"offset": -1}, {"limit": True}])
def test_export_bounds_before_io(wire, kwargs):
    with pytest.raises(ValueError):
        client().export_jobs(**kwargs)
    assert wire.calls == []


def test_non_json_response_rejected(wire):
    wire.content_type = "text/html"
    with pytest.raises(OpeningsAPIError, match="must be JSON"):
        client(mirror_fix_verified=True).add_posting(posting())


@pytest.mark.parametrize("slow_headers", [False, True])
def test_real_local_connection_closes_and_total_header_deadline(slow_headers):
    """A temporary synthetic peer verifies actual sockets, including Connection: close."""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(2)

        def serve():
            with listener.accept()[0] as peer:
                peer.settimeout(1)
                peer.recv(65536)
                try:
                    if slow_headers:
                        peer.sendall(b"HTTP/1.1 200 OK\r\n")
                        for _ in range(30):
                            peer.sendall(b"X-Synthetic: 1\r\n")
                            time.sleep(0.02)
                    else:
                        peer.sendall(
                            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                            b"Content-Length: 2\r\nConnection: close\r\n\r\n[]"
                        )
                except OSError:
                    pass

        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        started = time.monotonic()
        try:
            api = OpeningsAPI(
                host="127.0.0.1",
                port=listener.getsockname()[1],
                token="synthetic-token",
                timeout_seconds=0.15 if slow_headers else 1,
            )
            if slow_headers:
                with pytest.raises(OpeningsAPIError):
                    api.export_jobs()
                assert time.monotonic() - started < 1
            else:
                assert api.export_jobs() == ()
        finally:
            worker.join(timeout=2)
        assert not worker.is_alive()

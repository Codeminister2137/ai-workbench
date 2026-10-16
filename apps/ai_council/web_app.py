from __future__ import annotations

import argparse
import json
import socket
import threading
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast
from urllib.parse import urlparse

from config import DEFAULT_CONFIG_PATH, load_config
from council import LocalCouncil
from storage import DEFAULT_DB_PATH, ConversationStore

ROOT = Path(__file__).parent
STATIC_ROOT = ROOT / "web"
MAX_REQUEST_BYTES = 512_000
REQUEST_TIMEOUT_SECONDS = 5.0


class InvalidRequest(ValueError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class CouncilRequestHandler(SimpleHTTPRequestHandler):
    config_path = DEFAULT_CONFIG_PATH
    db_path = DEFAULT_DB_PATH

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_ROOT), **kwargs)

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(REQUEST_TIMEOUT_SECONDS)

    def _trusted_request(self) -> bool:
        port = cast(tuple[str, int], self.server.server_address)[1]
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        host = self.headers.get("Host")
        origin = self.headers.get("Origin")
        if (
            len(self.headers.get_all("Host", [])) != 1
            or host not in hosts
            or (origin is not None and origin != f"http://{host}")
        ):
            self.send_error(HTTPStatus.FORBIDDEN, "Untrusted request origin")
            return False
        return True

    def do_GET(self) -> None:
        if not self._trusted_request():
            return
        path = urlparse(self.path).path
        if path == "/":
            self.path = "/index.html"
            return super().do_GET()
        if path == "/api/config":
            return self._send_config()
        if path == "/api/conversations":
            return self._send_conversations()
        return super().do_GET()

    def do_POST(self) -> None:
        if not self._trusted_request():
            return
        path = urlparse(self.path).path
        if path == "/api/ask":
            return self._stream_ask()
        self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")

    def _send_json(self, payload: dict | list, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_config(self) -> None:
        config = load_config(self.config_path)
        self._send_json(
            {
                "default_conversation": config.default_conversation,
                "members": [
                    {
                        "name": member.name,
                        "model": member.model,
                        "temperature": member.temperature,
                    }
                    for member in config.members
                ],
            }
        )

    def _send_conversations(self) -> None:
        store = ConversationStore(self.db_path)
        try:
            self._send_json(store.list_conversations())
        finally:
            store.close()

    def _read_json_body(self) -> dict:
        media_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            raise InvalidRequest(415, "Content-Type must be application/json")
        lengths = self.headers.get_all("Content-Length", [])
        if self.headers.get("Transfer-Encoding") or len(lengths) != 1:
            raise InvalidRequest(400, "One Content-Length is required")
        try:
            length = int(lengths[0])
        except ValueError:
            raise InvalidRequest(400, "Invalid Content-Length") from None
        if not 0 < length <= MAX_REQUEST_BYTES:
            raise InvalidRequest(413, "Request body exceeds allowed size")
        expired = threading.Event()

        def abort_read():
            expired.set()
            try:
                self.connection.shutdown(socket.SHUT_RD)
            except OSError:
                pass

        timer = threading.Timer(REQUEST_TIMEOUT_SECONDS, abort_read)
        timer.daemon = True
        timer.start()
        try:
            raw = self.rfile.read(length)
            if expired.is_set() or len(raw) != length:
                raise InvalidRequest(408, "Incomplete request body")
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise InvalidRequest(400, "JSON body must be an object")
            return payload
        except (ValueError, UnicodeError) as exc:
            if isinstance(exc, InvalidRequest):
                raise
            raise InvalidRequest(400, "Invalid JSON body") from None
        except OSError:
            raise InvalidRequest(408, "Request body timed out") from None
        finally:
            timer.cancel()
            timer.join(timeout=1)

    def _stream_ask(self) -> None:
        try:
            payload = self._read_json_body()
            prompt = payload.get("prompt", "")
            conversation = payload.get("conversation", "")
            if not isinstance(prompt, str) or not isinstance(conversation, str):
                raise InvalidRequest(400, "Prompt and conversation must be strings")
            prompt = prompt.strip()
            conversation = conversation.strip() or None
            if not prompt:
                return self._send_json({"error": "Prompt is required."}, status=400)

            config = load_config(self.config_path)
            store = ConversationStore(self.db_path)
        except InvalidRequest as exc:
            self.close_connection = True
            return self._send_json({"error": str(exc)}, status=exc.status)
        except Exception:
            return self._send_json({"error": "Council configuration unavailable"}, status=500)

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        try:
            council = LocalCouncil(config, store)
            for event in council.ask_events(prompt, conversation_name=conversation):
                self._write_event(event)
        finally:
            store.close()
            self.close_connection = True

    def _write_event(self, event: dict) -> None:
        body = f"data: {json.dumps(event)}\n\n".encode()
        self.wfile.write(body)
        self.wfile.flush()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Local AI Council web UI.")
    parser.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1", "localhost"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    CouncilRequestHandler.config_path = args.config
    CouncilRequestHandler.db_path = args.db
    server = ThreadingHTTPServer((args.host, args.port), CouncilRequestHandler)
    print(f"Local AI Council web UI: http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()

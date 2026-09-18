from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from config import DEFAULT_CONFIG_PATH, load_config
from council import LocalCouncil
from storage import DEFAULT_DB_PATH, ConversationStore

ROOT = Path(__file__).parent
STATIC_ROOT = ROOT / "web"


class CouncilRequestHandler(SimpleHTTPRequestHandler):
    config_path = DEFAULT_CONFIG_PATH
    db_path = DEFAULT_DB_PATH

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_ROOT), **kwargs)

    def do_GET(self) -> None:
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
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length).decode("utf-8")
        return json.loads(raw_body) if raw_body else {}

    def _stream_ask(self) -> None:
        try:
            payload = self._read_json_body()
            prompt = str(payload.get("prompt", "")).strip()
            conversation = str(payload.get("conversation", "")).strip() or None
            if not prompt:
                return self._send_json({"error": "Prompt is required."}, status=400)

            config = load_config(self.config_path)
            store = ConversationStore(self.db_path)
        except Exception as exc:
            return self._send_json({"error": str(exc)}, status=500)

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
    parser.add_argument("--host", default="127.0.0.1")
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

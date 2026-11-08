"""Local Gmail digest slice 1: IMAP probe and offline fetch.

Local only: verifies the IMAP SSL login and reads the latest INBOX mails,
extracting plain metadata (from/date/subject/message-id/snippet/urls).
No hosted calls, no sending. Probe/fetch status output carries a coarse
reason class only and never contains secrets.
"""

from __future__ import annotations

import argparse
import contextlib
import email
import email.header
import email.policy
import imaplib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
IMAP_HOST = "imap.gmail.com"
SNIPPET_LEN = 200
MAX_URLS = 20
SUMMARY_MODEL = "muse-spark-1.3"
SUMMARY_INPUT_USD_PER_M = 1.25
SUMMARY_OUTPUT_USD_PER_M = 4.25
MAX_SUMMARY_CHARS = 60_000
SUMMARY_MAX_OUTPUT_TOKENS = 2048

_URL_RE = re.compile(r"https?://[^\s<>'\"]+")


def _load_loop_notify():
    spec = importlib.util.spec_from_file_location(
        "mail_digest_loop_notify", HERE / "loop_notify.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Reuse loop_notify's credential precedence (process env, repo-root .env,
# job-search prototype .env). Module-level alias so tests can monkeypatch it.
read_gmail_config = _load_loop_notify().read_gmail_config


def _classify(error: BaseException) -> str:
    """Map an exception to a coarse, secret-free reason class."""
    if isinstance(error, imaplib.IMAP4.error):
        return "auth"
    if isinstance(error, OSError):
        return "network"
    return "error"


def probe() -> tuple[bool, str]:
    """Verify the IMAP SSL login; return ``(ok, reason)``.

    ``reason`` is ``"ok"`` on success, otherwise one of
    ``missing-credentials`` / ``auth`` / ``network`` / ``error``.
    """
    config = read_gmail_config()
    if config is None:
        return False, "missing-credentials"
    address, password = config
    try:
        client = imaplib.IMAP4_SSL(IMAP_HOST)
    except Exception as error:
        return False, _classify(error)
    try:
        client.login(address, password)
    except Exception as error:
        return False, _classify(error)
    finally:
        with contextlib.suppress(Exception):
            client.logout()
    return True, "ok"


class DigestError(Exception):
    """Fetch failure carrying a coarse reason class only (never secrets)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    parts: list[str] = []
    for chunk, charset in email.header.decode_header(value):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(chunk)
    return "".join(parts)


def _message_text(msg: email.message.Message) -> str:
    """Best-effort plain text of a message; prefers text/plain parts."""
    if msg.is_multipart():
        plain: list[str] = []
        html: list[str] = []
        for part in msg.walk():
            if part.is_multipart():
                continue
            try:
                body = part.get_content()
            except Exception:
                continue
            if not isinstance(body, str):
                continue
            if part.get_content_type() == "text/plain":
                plain.append(body)
            elif part.get_content_type() == "text/html":
                html.append(body)
        if plain:
            return "\n".join(plain)
        return re.sub(r"<[^>]+>", " ", "\n".join(html))
    try:
        body = msg.get_content()
    except Exception:
        return ""
    return body if isinstance(body, str) else ""


def _extract_urls(text: str) -> list[str]:
    urls: list[str] = []
    for match in _URL_RE.findall(text):
        cleaned = match.rstrip(").,;:!?")
        if cleaned and cleaned not in urls:
            urls.append(cleaned)
        if len(urls) >= MAX_URLS:
            break
    return urls


def extract_message(raw: bytes) -> dict:
    """Local-only extraction: from/date/subject/message-id/snippet/urls."""
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    text = _message_text(msg)
    snippet = re.sub(r"\s+", " ", text).strip()[:SNIPPET_LEN]
    date = msg["Date"]
    return {
        "from": _decode_header(msg["From"]),
        "date": str(date) if date else "",
        "subject": _decode_header(msg["Subject"]),
        "message-id": _decode_header(msg["Message-ID"]),
        "snippet": snippet,
        "urls": _extract_urls(text),
    }


def fetch_latest(count: int) -> list[dict]:
    """Fetch the latest ``count`` INBOX mails, newest first.

    Raises :class:`DigestError` with a coarse reason on any failure.
    """
    config = read_gmail_config()
    if config is None:
        raise DigestError("missing-credentials")
    address, password = config
    try:
        client = imaplib.IMAP4_SSL(IMAP_HOST)
        client.login(address, password)
    except Exception as error:
        raise DigestError(_classify(error)) from None
    try:
        typ, _ = client.select("INBOX", readonly=True)
        if typ != "OK":
            raise DigestError("mailbox")
        typ, data = client.search(None, "ALL")
        if typ != "OK" or not data or not data[0]:
            return []
        nums = data[0].split()
        latest = nums[-count:] if count > 0 else []
        messages = []
        for num in reversed(latest):
            typ, fetched = client.fetch(num, "(RFC822)")
            if typ != "OK" or not fetched or not isinstance(fetched[0], tuple):
                continue
            messages.append(extract_message(fetched[0][1]))
        return messages
    except DigestError:
        raise
    except Exception as error:
        raise DigestError(_classify(error)) from None
    finally:
        with contextlib.suppress(Exception):
            client.logout()


def _meta_api_key() -> str | None:
    """Meta key from process env, else repository-root .env (never logged)."""
    key = os.environ.get("META_API_KEY", "").strip()
    if key:
        return key
    sys.path.insert(0, str(HERE.parent / "packages" / "ai_provider" / "src"))
    from ai_provider.secrets import read_secret_key

    try:
        return read_secret_key(HERE.parent / ".env", "META_API_KEY", label="Meta API credential")
    except (OSError, ValueError):
        return None


def _summary_client():
    sys.path.insert(0, str(HERE.parent / "packages" / "ai_provider" / "src"))
    from ai_provider.adapters.meta import MetaResponsesChatClient
    from ai_provider.config import BackendConfig, ProviderKind

    key = _meta_api_key()
    if not key:
        raise DigestError("missing-meta-key")
    return MetaResponsesChatClient(
        BackendConfig(provider=ProviderKind.META, model=SUMMARY_MODEL, api_key=key)
    )


def summarize_digest(messages: list, *, client=None) -> dict:
    """Summarize one local digest via Meta Standard (no-training route).

    Sends subject+snippet lines only, capped at MAX_SUMMARY_CHARS. Returns
    the summary text plus provider-reported usage and a USD estimate.
    """
    if not messages:
        raise DigestError("empty-digest")
    lines = []
    for item in messages:
        lines.append(f"- {item.get('subject', '')} | {item.get('snippet', '')}")
    body = "\n".join(lines)
    if len(body) > MAX_SUMMARY_CHARS:
        raise DigestError("digest-too-large")
    sys.path.insert(0, str(HERE.parent / "packages" / "ai_provider" / "src"))
    from ai_provider.contracts import (
        AIMessage,
        AIRequest,
        MessageRole,
        PrivacyClass,
    )

    actor = client or _summary_client()
    request = AIRequest(
        messages=(
            AIMessage(
                MessageRole.SYSTEM,
                "Summarize these mail items as short bullets: what each needs, "
                "if anything. Skip newsletters and noise in one line.",
            ),
            AIMessage(MessageRole.USER, body),
        ),
        model=SUMMARY_MODEL,
        max_output_tokens=SUMMARY_MAX_OUTPUT_TOKENS,
        privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
    )
    try:
        response = actor.complete(request)
    except DigestError:
        raise
    except Exception as error:
        raise DigestError(_classify(error)) from None
    if str(response.finish_reason) == "length":
        raise DigestError("summary-truncated")
    usage = response.usage
    estimate = (
        (usage.input_tokens or 0) * SUMMARY_INPUT_USD_PER_M
        + (usage.output_tokens or 0) * SUMMARY_OUTPUT_USD_PER_M
    ) / 1_000_000
    return {
        "summary": response.message.content,
        "model": SUMMARY_MODEL,
        "finish_reason": str(response.finish_reason),
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "estimated_usd": round(estimate, 6),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--probe", action="store_true", help="verify IMAP SSL login")
    group.add_argument("--fetch", type=int, metavar="N", help="fetch latest N INBOX mails")
    group.add_argument(
        "--summarize", type=Path, metavar="DIGEST", help="summarize a digest JSON via hosted model"
    )
    parser.add_argument(
        "--out", type=Path, default=None, help="JSON output path for --fetch/--summarize"
    )
    args = parser.parse_args(argv)
    if args.probe:
        ok, reason = probe()
        print("PROBE_OK" if ok else f"PROBE_FAIL {reason}")
        return 0 if ok else 1
    if args.summarize is not None:
        if args.out is None:
            parser.error("--summarize requires --out <json>")
        try:
            messages = json.loads(args.summarize.read_text(encoding="utf-8"))
            result = summarize_digest(messages)
        except DigestError as error:
            print(f"SUMMARIZE_FAIL {error.reason}")
            return 1
        args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"SUMMARIZE_OK {result['estimated_usd']}")
        return 0
    if args.fetch is None or args.fetch < 1:
        parser.error("--fetch N requires N >= 1")
    if args.out is None:
        parser.error("--fetch requires --out <json>")
    try:
        messages = fetch_latest(args.fetch)
    except DigestError as error:
        print(f"FETCH_FAIL {error.reason}")
        return 1
    args.out.write_text(json.dumps(messages, indent=2), encoding="utf-8")
    print(f"FETCH_OK {len(messages)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

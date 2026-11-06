"""Shared host loop for single-shot model development slices.

One provider-agnostic core drives the proven slice protocol: the model
proposes complete file sources as JSON; the host applies them to
allowlisted paths, validates (compile + test-growth + pytest + ruff),
restores pre-slice bytes on rejection, and retries with failure
excerpts. Providers differ only in their thin driver (client factory,
model id, credential name, purpose tag) — the orchestration lives here
exactly once.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path

PROMPT_BOUND = 60000
RESPONSE_BOUND = 1048576
TIMEOUT = 150.0


def slice_arg_parser(description: str) -> argparse.ArgumentParser:
    """CLI shared by every slice driver (same flags, same bounds)."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--slice", required=True)
    parser.add_argument("--brief", type=Path, required=True)
    parser.add_argument("--allow", action="append", required=True)
    parser.add_argument("--pytest", action="append", default=[])
    parser.add_argument("--phase-dir", type=Path, required=True)
    parser.add_argument("--max-calls", type=int, default=4)
    parser.add_argument("--cap", type=int, default=16384)
    return parser


def read_env_key(root: Path, env_name: str, *, label: str) -> str:
    """Read exactly one credential from the repo .env (no fallback)."""
    from ai_provider.secrets import read_secret_key

    try:
        return read_secret_key(root / ".env", env_name, label=label)
    except ValueError as exc:
        raise ValueError(f"Exactly one {label} is required ({exc})") from exc


def parse_changes(text: str) -> dict:
    """Extract {path: source} from the model's JSON envelope."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Model response contained no JSON object")
    value = json.loads(text[start : end + 1])
    if not isinstance(value, dict) or not isinstance(value.get("changes"), dict):
        raise ValueError("Model JSON must be {changes: {path: source}}")
    return value["changes"]


def apply_changes(root: Path, changes: dict, allow: set[str]) -> list[str]:
    """Write allowlisted sources, preserving the repo's CRLF endings."""
    written = []
    for name, source in changes.items():
        if name not in allow or not isinstance(source, str):
            raise ValueError(f"Refusing non-allowlisted change: {name!r}")
        target = root / name
        old = target.read_bytes() if target.exists() else b""
        # Preserve the repo's CRLF endings: the model emits LF.
        text = source.replace("\r\n", "\n")
        if old.count(b"\r\n") > old.count(b"\n") - old.count(b"\r\n"):
            text = text.replace("\n", "\r\n")
        target.write_bytes(text.encode("utf-8"))
        written.append(name)
    return written


def run_checks(root: Path, pytest_files: list[str], changed: list[str]) -> tuple[bool, str]:
    """Run pytest + ruff on the host; formatting is host-applied."""
    import sys as _sys

    py = root / ".venv/Scripts/python.exe"
    interpreter = str(py) if py.exists() else _sys.executable
    out: list[str] = []
    ok_all = True
    if pytest_files:
        proc = subprocess.run(
            [interpreter, "-m", "pytest", *pytest_files, "-q"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=600,
        )
        out.append(f"pytest exit={proc.returncode}\n{proc.stdout[-2000:]}{proc.stderr[-2000:]}")
        ok_all = ok_all and proc.returncode == 0
    py_files = [f for f in changed if f.endswith(".py")]
    if py_files:
        # Formatting and safe fixes are deterministic host work: apply, then verify.
        subprocess.run(
            [interpreter, "-m", "ruff", "check", "--fix", *py_files],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=120,
        )
        subprocess.run(
            [interpreter, "-m", "ruff", "format", *py_files],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=120,
        )
        for cmd in (
            ["-m", "ruff", "check", *py_files],
            ["-m", "ruff", "format", "--check", *py_files],
        ):
            proc = subprocess.run(
                [interpreter, *cmd], cwd=root, capture_output=True, text=True, timeout=120
            )
            out.append(
                f"ruff {' '.join(cmd[1:3])} exit={proc.returncode}\n{proc.stdout[-1000:]}{proc.stderr[-1000:]}"
            )
            ok_all = ok_all and proc.returncode == 0
    return ok_all, "\n".join(out)


def drive_slice(
    *,
    root: Path,
    client,
    model: str,
    slice_name: str,
    brief: str,
    allow: set[str],
    pytest_files: list[str],
    phase: Path,
    max_calls: int,
    cap: int,
    purpose: str,
) -> dict:
    """Run the send/validate/retry loop; returns the final receipt dict."""
    from ai_provider.contracts import AIMessage, AIRequest, MessageRole, PrivacyClass

    if not brief.strip() or len(brief) > 4000:
        raise ValueError("Brief must be 1..4000 chars")
    phase.mkdir(parents=True, exist_ok=False)

    def _read_allowlist() -> dict:
        return {
            name: (root / name).read_text(encoding="utf-8") if (root / name).exists() else ""
            for name in allow
        }

    files = _read_allowlist()
    pristine = dict(files)
    pristine_bytes = {
        name: (root / name).read_bytes() if (root / name).exists() else None for name in allow
    }
    receipt: dict = {"slice": slice_name, "model": model, "sends": [], "status": "running"}
    (phase / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    feedback = ""
    for attempt in range(1, max_calls + 1):
        prompt = (
            brief
            + "\nYou are the implementer. Return only JSON: "
            + '{"changes":{"allowlisted/path.py":"complete UTF-8 source (LF endings)"}}. '
            + "Change ONLY allowlisted files. No shell, no new dependencies, no scope "
            + "changes. Match surrounding code style.\n"
            + json.dumps({"allowlist": sorted(allow), "files": files}, ensure_ascii=False)
            + feedback
        )
        if len(prompt.encode()) > PROMPT_BOUND:
            receipt["sends"].append(
                {"attempt": attempt, "status": "prompt_over_bound", "bytes": len(prompt.encode())}
            )
            receipt["status"] = "failed"
            break
        send = {"attempt": attempt, "status": "sending"}
        receipt["sends"].append(send)
        request = AIRequest(
            messages=(AIMessage(role=MessageRole.USER, content=prompt),),
            model=model,
            max_output_tokens=cap,
            privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
            metadata={"purpose": purpose, "slice": slice_name},
        )
        started = time.perf_counter()
        try:
            response = client.complete(request)
        except Exception as exc:
            send.update(status="transport_failed", error=f"{type(exc).__name__}: {exc}"[:300])
            break
        content = response.message.content or ""
        send.update(
            status="received",
            elapsed_seconds=round(time.perf_counter() - started, 1),
            finish_reason=response.finish_reason.value,
            usage=dataclasses.asdict(response.usage) if response.usage else None,
            response_sha256=hashlib.sha256(content.encode()).hexdigest(),
        )
        if response.finish_reason.value != "stop":
            send["status"] = f"bad_finish_{response.finish_reason.value}"
            break
        if len(content.encode()) > RESPONSE_BOUND:
            send["status"] = "oversized"
            break
        try:
            changes = parse_changes(content)
            written = apply_changes(root, changes, allow)
            # Refuse double-encoded garbage before it can poison the tree:
            # Python sources must compile and contain real newlines.
            for name in written:
                if name.endswith(".py"):
                    src = (root / name).read_text(encoding="utf-8")
                    if "\n" not in src:
                        raise ValueError(f"{name}: no real newlines (escaped?)")
                    compile(src, name, "exec")
            test_paths = [n for n in allow if "/tests/" in n or n.startswith("tests/")]

            def _test_count(data: bytes) -> int:
                return len(re.findall(rb"^def (test_\w+)", data, re.MULTILINE))

            if test_paths:
                before = sum(_test_count(pristine_bytes.get(n) or b"") for n in test_paths)
                after = sum(_test_count((root / n).read_bytes()) for n in test_paths)
                # Tests must grow: byte-diffs alone once hid a file swap.
                if after <= before and not any(pristine_bytes.get(n) is None for n in test_paths):
                    raise ValueError("allowlisted tests gained no test functions")
        except (ValueError, SyntaxError) as exc:
            send["status"] = f"rejected: {exc}"[:200]
            # Restore pre-slice bytes so the retry starts from real sources.
            for name, original in pristine_bytes.items():
                target = root / name
                if original is None:
                    target.unlink(missing_ok=True)
                else:
                    target.write_bytes(original)
            (phase / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
            feedback = (
                "\nYOUR FILES WERE REJECTED WITHOUT RUNNING TESTS: "
                f"{exc}. The tree was restored to the original sources. "
                "Return RAW file sources with real newlines, "
                "not JSON-escaped string literals. Full files again.\n"
            )
            files = dict(pristine)
            continue
        send["written"] = written
        ok, output = run_checks(root, pytest_files, written)
        send["checks_passed"] = ok
        send["check_output"] = output[-3000:]
        (phase / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        if ok:
            receipt["status"] = "accepted"
            break
        feedback = (
            "\nPREVIOUS ATTEMPT FAILED HOST CHECKS. Fix and return full files again.\n"
            + output[-3000:]
        )
        files = _read_allowlist()
    else:
        receipt["status"] = "attempts_exhausted"
    if receipt["status"] == "running":
        receipt["status"] = "failed"
    (phase / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


def print_summary(receipt: dict) -> None:
    """Print the slice outcome + spend totals (same shape as before)."""
    print(
        json.dumps(
            {
                "slice": receipt["slice"],
                "status": receipt["status"],
                "sends": len(receipt["sends"]),
            }
        )
    )
    # Print usage totals for the spend log.
    totals = {"input": 0, "output": 0}
    for send in receipt["sends"]:
        usage = send.get("usage") or {}
        totals["input"] += usage.get("input_tokens") or 0
        totals["output"] += usage.get("output_tokens") or 0
    print(json.dumps({"usage_tokens": totals}))

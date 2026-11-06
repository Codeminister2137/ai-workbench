"""Drive one development slice through the Baseten event model.

Run from the repo root. The model proposes complete file sources as JSON;
the host applies them to the working tree, runs pytest + ruff (formatting
is host-applied), and retries with failure excerpts. Bounds: prompt 60KB
(~35KB of files max — split bigger slices), response 1MB, finite sends,
allowlisted files only. The model gets no shell: validation runs on the
host. Rejected files restore pre-slice bytes. Receipt per slice under the
given phase dir (must be fresh). Host MUST still review the diff: the model
occasionally emits stray edits and skips required tests.

Proven 2026-11-06 (9 accepted slices). Usage:
    python scripts/baseten-slice-develop.py --slice NAME --brief BRIEF.txt
        --allow path/a.py [--allow ...] --pytest tests/test_x.py
        --phase-dir artifacts/<run>/<slice> [--max-calls 4] [--cap 16384]
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "packages/ai_provider/src")

from ai_provider.adapters.baseten import BASETEN_BASE_URL, BasetenChatClient
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.contracts import AIMessage, AIRequest, MessageRole, PrivacyClass

MODEL = "meta-models/muse-spark-open-1026"
ENV_NAME = "BASETEN_HACKATHON_API_KEY"
PROMPT_BOUND = 60000
RESPONSE_BOUND = 1048576
TIMEOUT = 150.0


def read_key(root: Path) -> str:
    values = [
        line.partition("=")[2].strip().strip("\"'")
        for line in (root / ".env").read_text(encoding="utf-8-sig").splitlines()
        if line.partition("=")[0].strip() == ENV_NAME
    ]
    if len(values) != 1 or not values[0]:
        raise ValueError("Exactly one Baseten event credential is required")
    return values[0]


class LowReasoningClient(BasetenChatClient):
    def _chat_payload(self, request, *, stream):
        payload = super()._chat_payload(request, stream=stream)
        payload["reasoning_effort"] = "low"
        return payload


def parse_changes(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Model response contained no JSON object")
    value = json.loads(text[start : end + 1])
    if not isinstance(value, dict) or not isinstance(value.get("changes"), dict):
        raise ValueError("Model JSON must be {changes: {path: source}}")
    return value["changes"]


def apply_changes(root: Path, changes: dict, allow: set[str]) -> list[str]:
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
    py = root / ".venv/Scripts/python.exe"
    out: list[str] = []
    ok_all = True
    if pytest_files:
        proc = subprocess.run(
            [str(py), "-m", "pytest", *pytest_files, "-q"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=600,
        )
        out.append(f"pytest exit={proc.returncode}\n{proc.stdout[-2000:]}{proc.stderr[-2000:]}")
        ok_all = ok_all and proc.returncode == 0
    py_files = [f for f in changed if f.endswith(".py")]
    if py_files:
        # Formatting is deterministic host work: apply it, then verify.
        subprocess.run(
            [str(py), "-m", "ruff", "format", *py_files],
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
                [str(py), *cmd], cwd=root, capture_output=True, text=True, timeout=120
            )
            out.append(
                f"ruff {' '.join(cmd[1:3])} exit={proc.returncode}\n{proc.stdout[-1000:]}{proc.stderr[-1000:]}"
            )
            ok_all = ok_all and proc.returncode == 0
    return ok_all, "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slice", required=True)
    parser.add_argument("--brief", type=Path, required=True)
    parser.add_argument("--allow", action="append", required=True)
    parser.add_argument("--pytest", action="append", default=[])
    parser.add_argument("--phase-dir", type=Path, required=True)
    parser.add_argument("--max-calls", type=int, default=4)
    parser.add_argument("--cap", type=int, default=16384)
    args = parser.parse_args()

    root = Path.cwd()
    brief = args.brief.read_text(encoding="utf-8")
    if not brief.strip() or len(brief) > 4000:
        raise ValueError("Brief must be 1..4000 chars")
    allow = set(args.allow)
    phase = args.phase_dir
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

    client = LowReasoningClient(
        BackendConfig(
            provider=ProviderKind.BASETEN,
            model=MODEL,
            base_url=BASETEN_BASE_URL,
            api_key=read_key(root),
            timeout_seconds=TIMEOUT,
        )
    )
    receipt: dict = {"slice": args.slice, "model": MODEL, "sends": [], "status": "running"}
    (phase / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    feedback = ""
    for attempt in range(1, args.max_calls + 1):
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
            model=MODEL,
            max_output_tokens=args.cap,
            privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
            metadata={"purpose": "baseten-slice", "slice": args.slice},
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
        ok, output = run_checks(root, args.pytest, written)
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
    print(
        json.dumps(
            {"slice": args.slice, "status": receipt["status"], "sends": len(receipt["sends"])}
        )
    )
    # Print usage totals for the spend log.
    totals = {"input": 0, "output": 0}
    for send in receipt["sends"]:
        usage = send.get("usage") or {}
        totals["input"] += usage.get("input_tokens") or 0
        totals["output"] += usage.get("output_tokens") or 0
    print(json.dumps({"usage_tokens": totals}))
    return 0 if receipt["status"] == "accepted" else 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Scripted end-to-end rehearsal for the remote-operator serve API ($0, localhost).

Drives the full task lifecycle over HTTP the same way the phone UI does:
create -> run -> review -> approve -> verify, plus a reject-path task and
event coverage. Intended to run against a scripted-mode serve on localhost.

Secrets (OPERATOR_ACCESS_TOKEN, nonces) are read at runtime and never
printed; nonce/token-looking values in output are redacted to their last
4 characters.

Usage (from ai-workbench):
  .venv/Scripts/python.exe patches/operator-rehearsal/rehearse.py ^
    --env-file C:/Users/Jakub/PycharmProjects/remote-ai-operator/.env
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path


def load_token(env_file: Path) -> str:
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("OPERATOR_ACCESS_TOKEN="):
            return line.split("=", 1)[1].strip().strip("'\"")
    raise SystemExit(f"OPERATOR_ACCESS_TOKEN not found in {env_file}")


def redact(obj):
    if isinstance(obj, dict):
        return {
            k: ("***" + str(v)[-4:] if "nonce" in k.lower() or "token" in k.lower() else redact(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj


class Client:
    def __init__(self, base: str, token: str):
        self.base = base.rstrip("/")
        self.token = token

    def call(self, method: str, path: str, body: dict | None = None):
        data = json.dumps(body or {}).encode() if method != "GET" else None
        req = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
            headers={
                "Authorization": "Bearer " + self.token,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode()
                return resp.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode()[:500]
            except OSError:
                detail = ""
            return exc.code, {"http_error": detail}


def check(name: str, cond: bool, detail: object = "") -> None:
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {json.dumps(redact(detail))[:300]}")
    if not cond:
        raise SystemExit(f"rehearsal failed at: {name}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8765")
    ap.add_argument("--env-file", required=True, type=Path)
    ap.add_argument("--prompt", default="Rehearsal: summarize repo health in one line (scripted)")
    args = ap.parse_args()

    client = Client(args.base, load_token(args.env_file))

    # Task 1: full approve path.
    code, created = client.call("POST", "/api/tasks", {"prompt": args.prompt})
    check("create task", code == 200 and "id" in created, {"code": code, **created})
    task_id = created["id"]

    code, run = client.call("POST", f"/api/tasks/{task_id}/run", {})
    check("run task", code == 200, {"code": code, **run})

    code, review = client.call("GET", f"/api/tasks/{task_id}")
    task = review.get("task", {}) if isinstance(review, dict) else {}
    check("review task", code == 200 and task.get("status"), {"code": code, "task": task})
    approval = task.get("approval") or {}
    nonce = approval.get("nonce")
    check("nonce present", bool(nonce), {"nonce": nonce})

    code, approved = client.call("POST", f"/api/tasks/{task_id}/approve", {"nonce": nonce})
    check("approve task", code == 200, {"code": code, **approved})

    code, final = client.call("GET", f"/api/tasks/{task_id}")
    final_task = final.get("task", {}) if isinstance(final, dict) else {}
    check(
        "final status completed",
        code == 200 and final_task.get("status") == "completed",
        {"code": code, "status": final_task.get("status")},
    )

    code, events = client.call("GET", f"/api/tasks/{task_id}/events?after=0")
    check(
        "events covered",
        code == 200 and isinstance(events, list) and len(events) > 0,
        {"code": code, "count": len(events) if isinstance(events, list) else "?"},
    )

    # Task 2: reject path.
    code, created2 = client.call(
        "POST", "/api/tasks", {"prompt": "Rehearsal reject-path probe (scripted)"}
    )
    check("create task 2", code == 200 and "id" in created2, {"code": code, **created2})
    task2 = created2["id"]
    code, _ = client.call("POST", f"/api/tasks/{task2}/run", {})
    check("run task 2", code == 200, {"code": code})
    code, rejected = client.call("POST", f"/api/tasks/{task2}/reject", {})
    check("reject task 2", code == 200, {"code": code, **rejected})
    code, final2 = client.call("GET", f"/api/tasks/{task2}")
    final2_task = final2.get("task", {}) if isinstance(final2, dict) else {}
    check(
        "task 2 terminal",
        code == 200 and final2_task.get("status"),
        {"code": code, "status": final2_task.get("status")},
    )

    print("REHEARSAL OK")


if __name__ == "__main__":
    main()

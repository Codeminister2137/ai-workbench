"""Weekly wake-path self-test: mail the owner only on failure.

Local checks for the remote-wake chain that can regress silently:
dashboard serve, NIC wake-armed state, LAN-IP drift (the FunBox cannot
pin a static lease, so the self-test guards the forward target instead),
public-IP lookup, DDNS hostname
resolution (when configured), and Gmail SMTP login (no mail sent).
Success appends one log line; any failure sends a single owner mail.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import smtplib
import socket
import ssl
import subprocess
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location("loop_notify_mod", HERE / "loop_notify.py")
assert _SPEC is not None and _SPEC.loader is not None
loop_notify = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(loop_notify)

NETWORK_DEVICE = re.compile(r"ethernet|gbe|wi-?fi|wlan|realtek|intel", re.IGNORECASE)
DDNS_ENV = "WAKE_DDNS_HOSTNAME"
LAN_ENV = "WAKE_LAN_IP"


def primary_lan_ip() -> str | None:
    """Primary outbound IPv4 without sending traffic (UDP connect trick)."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()


def check_lan_ip(expected: str | None = None, probe=primary_lan_ip) -> tuple[bool, str]:
    """Require the PC to hold the LAN IP the wake forward targets.

    Expected comes from the argument or WAKE_LAN_IP (env, else repo .env);
    pending when unconfigured, since a downloader's LAN always differs.
    """
    import os

    exp = (expected or "").strip() or os.environ.get(LAN_ENV, "").strip()
    if not exp:
        try:
            from ai_provider.secrets import read_dotenv_values

            found = read_dotenv_values(loop_notify.ROOT / ".env", {LAN_ENV})
            exp = (found.get(LAN_ENV) or "").strip()
        except Exception:  # noqa: BLE001 - missing helper means not configured
            exp = ""
    if not exp:
        return True, "pending (WAKE_LAN_IP not configured)"
    try:
        actual = probe()
    except Exception as exc:  # noqa: BLE001 - self-test reports, never raises
        return False, f"{type(exc).__name__}: {exc}"[:200]
    if not actual:
        return False, "primary LAN IP undeterminable"
    if actual == exp:
        return True, f"holds {actual} (forward target {exp})"
    return False, f"drift: PC holds {actual}, forward targets {exp}"


def check_dashboard(dashboard: str, *, timeout: float = 10) -> tuple[bool, str]:
    """Probe the local dashboard status endpoint."""
    try:
        with urllib.request.urlopen(
            f"{dashboard.rstrip('/')}/api/status", timeout=timeout
        ) as response:
            body = response.read(200).decode("utf-8", errors="replace")
        return True, f"HTTP 200 ({body[:80]})"
    except Exception as exc:  # noqa: BLE001 - self-test reports, never raises
        return False, f"{type(exc).__name__}: {exc}"[:200]


def check_wake_armed(runner=subprocess.run) -> tuple[bool, str]:
    """Require a network adapter in the wake-armed device list."""
    try:
        proc = runner(
            ["powercfg", "/devicequery", "wake_armed"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:  # noqa: BLE001 - self-test reports, never raises
        return False, f"{type(exc).__name__}: {exc}"[:200]
    for line in proc.stdout.splitlines():
        if NETWORK_DEVICE.search(line):
            return True, line.strip()[:120]
    return False, f"no network adapter armed ({proc.stdout.strip()[:120] or 'empty'})"


def check_public_ip(lookup=loop_notify.public_ip) -> tuple[bool, str]:
    """Require a successful public-IP lookup."""
    address = lookup()
    if address:
        return True, address
    return False, "api.ipify.org unreachable or implausible answer"


def check_ddns(resolve=socket.gethostbyname) -> tuple[bool, str]:
    """Resolve the DDNS hostname when configured; pending otherwise."""
    import os

    hostname = os.environ.get(DDNS_ENV, "").strip()
    if not hostname:
        try:
            from ai_provider.secrets import read_dotenv_values

            found = read_dotenv_values(loop_notify.ROOT / ".env", {DDNS_ENV})
            hostname = (found.get(DDNS_ENV) or "").strip()
        except Exception:  # noqa: BLE001 - missing helper means not configured
            hostname = ""
    if not hostname:
        return True, "pending (WAKE_DDNS_HOSTNAME not configured)"
    try:
        return True, f"{hostname} -> {resolve(hostname)}"
    except Exception as exc:  # noqa: BLE001 - self-test reports, never raises
        return False, f"{hostname}: {type(exc).__name__}"[:200]


def check_smtp_login(
    read_config=loop_notify.read_gmail_config, smtp_class=smtplib.SMTP
) -> tuple[bool, str]:
    """Verify Gmail SMTP login without sending any mail."""
    config = read_config()
    if config is None:
        return False, "gmail credentials not configured"
    address, password = config
    try:
        with smtp_class("smtp.gmail.com", 587, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            smtp.login(address, password)
        return True, "login ok (no mail sent)"
    except Exception as exc:  # noqa: BLE001 - self-test reports, never raises
        return False, f"{type(exc).__name__}"[:200]


CHECKS = (
    ("dashboard", check_dashboard),
    ("wake_armed", check_wake_armed),
    ("lan_ip", check_lan_ip),
    ("public_ip", check_public_ip),
    ("ddns", check_ddns),
    ("smtp_login", check_smtp_login),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=HERE.parent)
    parser.add_argument("--dashboard", default="http://127.0.0.1:8766")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-mail", action="store_true")
    args = parser.parse_args(argv)

    results = [
        (name, *fn(args.dashboard)) if name == "dashboard" else (name, *fn()) for name, fn in CHECKS
    ]
    failures = [(name, detail) for name, ok, detail in results if not ok]
    stamp = datetime.now(UTC).isoformat()
    print(f"wake self-test: {len(results) - len(failures)}/{len(results)} ok")
    for name, ok, detail in results:
        print(f"  {'ok' if ok else 'FAIL'} {name}: {detail}")

    run_dir = args.repo_root / "artifacts" / "wake-self-test"
    if not failures and not args.force_mail:
        if not args.dry_run:
            run_dir.mkdir(parents=True, exist_ok=True)
            with (run_dir / "runs.log").open("a", encoding="utf-8") as handle:
                handle.write(f"{stamp} ok={len(results)}\n")
        return 0
    if args.dry_run:
        print("dry-run: would send failure mail" if failures else "dry-run: success, silent")
        return 0 if not failures else 1
    gmail = loop_notify.read_gmail_config(args.repo_root)
    if gmail is None:
        print("cannot mail: gmail credentials not configured", file=sys.stderr)
        return 1
    address, password = gmail
    owner_mail = loop_notify._load_owner_mail()
    body = "\n".join(
        ["Wake-path self-test FAILED:", ""]
        + [f"- {name}: {detail}" for name, detail in failures]
        + ["", "Successful checks:", ""]
        + [f"- {name}: {detail}" for name, ok, detail in results if ok]
    )
    owner_mail.send_owner_mail(
        to=address,
        subject="Wake self-test FAILED",
        body=body,
        config={
            "owner": address,
            "host": "smtp.gmail.com",
            "port": 587,
            "username": address,
            "password": password,
            "starttls": True,
        },
        dry_run=False,
        receipts_dir=run_dir,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

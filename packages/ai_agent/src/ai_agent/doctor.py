"""Preflight diagnostics: one fix-it list for a fresh checkout (gap G1).

Offline probes only: interpreter/venv, uv, Ollama reachability plus
installed models, native-client binaries, ``.env``/catalog presence.
Every probe is fail-soft and prints names, never secret values.
Diagnostic only; nothing here changes behavior.
"""

from __future__ import annotations

import json
import shutil
import sys
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CATALOG = Path("packages/ai_orchestrator/examples/model_catalog.toml")
OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"
REQUIRED_PYTHON = (3, 13)


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    """One probe outcome; optional failures print but keep exit code 0."""

    name: str
    ok: bool
    detail: str
    fix: str = ""
    required: bool = True


def _python_check() -> DoctorCheck:
    ok = sys.version_info >= REQUIRED_PYTHON
    detail = ".".join(str(part) for part in sys.version_info[:3])
    return DoctorCheck(
        name="python",
        ok=ok,
        detail=detail,
        fix="" if ok else "Install Python 3.13+ and re-run inside it.",
    )


def _venv_check() -> DoctorCheck:
    ok = sys.prefix != sys.base_prefix
    return DoctorCheck(
        name="venv",
        ok=ok,
        detail=sys.prefix,
        fix="" if ok else "Activate the repo .venv before running agent commands.",
    )


def _which_check(name: str, fix: str, *, which: Callable[[str], str | None]) -> DoctorCheck:
    found = which(name)
    return DoctorCheck(
        name=name, ok=found is not None, detail=found or "not on PATH", fix="" if found else fix
    )


def _repo_venv_check(repo_root: Path) -> DoctorCheck:
    candidate = (
        repo_root / ".venv" / "Scripts" / "python.exe"
        if sys.platform == "win32"
        else repo_root / ".venv" / "bin" / "python"
    )
    ok = candidate.is_file()
    return DoctorCheck(
        name="repo .venv",
        ok=ok,
        detail=str(candidate) if ok else "missing",
        fix="" if ok else "Create the repo venv (see docs/installation.md).",
    )


def _ollama_check(
    urlopen: Callable[..., Any] = urllib.request.urlopen,
) -> DoctorCheck:
    try:
        with urlopen(OLLAMA_TAGS_URL, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("unexpected tags shape")
    except Exception:  # noqa: BLE001 - any transport failure is "down"
        return DoctorCheck(
            name="ollama",
            ok=False,
            detail="unreachable",
            fix="Start Ollama (ollama serve) for local routes.",
        )
    models = [
        str(item.get("name", "?"))
        for item in (payload.get("models") or [])
        if isinstance(item, dict)
    ]
    detail = f"{len(models)} model(s): {', '.join(models[:8])}" if models else "up, no models"
    fix = "" if models else "Pull at least one model (ollama pull <name>)."
    return DoctorCheck(name="ollama", ok=True, detail=detail, fix=fix)


def _client_checks(
    resolve: Callable[[object], str | None] | None = None,
) -> tuple[DoctorCheck, ...]:
    from ai_orchestrator import AccessMethod
    from ai_provider.external_agents import external_agent_command

    discover = resolve or external_agent_command
    methods = (
        ("codex", AccessMethod.CODEX_CLI),
        ("gemini", AccessMethod.GEMINI_CLI),
        ("antigravity", AccessMethod.ANTIGRAVITY_CLI),
        ("copilot", AccessMethod.COPILOT_CLI),
        ("kiro", AccessMethod.KIRO_CLI),
    )
    checks: list[DoctorCheck] = []
    for label, method in methods:
        try:
            command = discover(method)
        except Exception:  # noqa: BLE001 - discovery must stay fail-soft
            command = None
        checks.append(
            DoctorCheck(
                name=f"client:{label}",
                ok=command is not None,
                detail=command or "not installed",
                fix="" if command else f"Optional: install {label} CLI to enable that route.",
                required=False,
            )
        )
    return tuple(checks)


def _dotenv_check(repo_root: Path) -> DoctorCheck:
    ok = (repo_root / ".env").is_file()
    return DoctorCheck(
        name=".env",
        ok=ok,
        detail="present" if ok else "missing",
        fix="" if ok else "Optional: copy .env.example to .env for keyed routes.",
        required=False,
    )


def _catalog_check(repo_root: Path) -> DoctorCheck:
    from ai_orchestrator.catalog import load_model_catalog

    path = repo_root / DEFAULT_CATALOG
    if not path.is_file():
        return DoctorCheck(
            name="catalog",
            ok=False,
            detail="missing",
            fix=f"Restore {DEFAULT_CATALOG.as_posix()} (agent routing needs it).",
        )
    try:
        entries = load_model_catalog(path)
    except Exception as exc:  # noqa: BLE001 - report, don't crash
        return DoctorCheck(
            name="catalog",
            ok=False,
            detail=f"unparseable: {type(exc).__name__}",
            fix=f"Fix {DEFAULT_CATALOG.as_posix()} (must define a 'models' array).",
        )
    return DoctorCheck(name="catalog", ok=True, detail=f"{len(entries)} entries")


def run_doctor(
    repo_root: Path | None = None,
    *,
    which: Callable[[str], str | None] | None = None,
    urlopen: Callable[..., Any] | None = None,
    client_command: Callable[[object], str | None] | None = None,
) -> tuple[DoctorCheck, ...]:
    """Run every probe; never raises, never prints secrets."""
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    # Resolved late so tests can patch shutil/urlopen entry points.
    which_fn = which or shutil.which
    urlopen_fn = urlopen or urllib.request.urlopen
    return (
        _python_check(),
        _venv_check(),
        _which_check("uv", "Install uv (see docs/installation.md).", which=which_fn),
        _repo_venv_check(root),
        _ollama_check(urlopen_fn),
        *_client_checks(client_command),
        _dotenv_check(root),
        _catalog_check(root),
    )


def format_report(checks: Sequence[DoctorCheck]) -> str:
    """Render the checklist plus one fix-it list."""
    lines = ["Workbench doctor:"]
    for check in checks:
        mark = "ok" if check.ok else ("WARN" if not check.required else "FAIL")
        lines.append(f"[{mark}] {check.name}: {check.detail}")
    fixes = [f"- {check.name}: {check.fix}" for check in checks if not check.ok and check.fix]
    if fixes:
        lines.append("Fix:")
        lines.extend(fixes)
    else:
        lines.append("All required checks passed.")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for `ai-assistant doctor`; 0 iff required checks pass."""
    import argparse

    parser = argparse.ArgumentParser(prog="ai-assistant doctor", description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args(argv)
    repo_root = args.repo_root
    if repo_root is None:
        try:
            from ai_agent.repo_coding_assistant import find_repo_root

            repo_root = find_repo_root(Path.cwd())
        except Exception:  # noqa: BLE001 - fall back to cwd
            repo_root = Path.cwd()
    checks = run_doctor(repo_root)
    print(format_report(checks))
    return 0 if all(check.ok for check in checks if check.required) else 1

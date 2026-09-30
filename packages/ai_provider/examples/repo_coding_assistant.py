from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

# Keep this example executable from a source checkout without requiring install.
# The implementation lives in the package module; this file is a compatibility
# shim for old example imports and tests.
_REPO_ROOT = Path(__file__).resolve().parents[3]
for _package_dir in (
    _REPO_ROOT / "packages" / "ai_provider" / "src",
    _REPO_ROOT / "packages" / "ai_orchestrator" / "src",
    _REPO_ROOT / "packages" / "ai_agent" / "src",
):
    if _package_dir.exists() and str(_package_dir) not in sys.path:
        sys.path.insert(0, str(_package_dir))

# Imports below use the repository's source layout when this module is run directly.
# ruff: noqa: E402, I001
from ai_provider import repo_coding_assistant as _impl
from ai_provider.external_agents import (
    _external_agent_result_from_completed_process,
)
from ai_provider.repo_context import _limit_context_content as _limit_context_content


_ORIGINALS: dict[str, Any] = {
    "create_chat_client": _impl.create_chat_client,
    "run_auxiliary_panel": _impl.run_auxiliary_panel,
    "run_coding_prompt": _impl.run_coding_prompt,
    "run_local_context_delegation": _impl.run_local_context_delegation,
    "run_codex_plugin_operation": _impl.run_codex_plugin_operation,
    "setup_project_codex_mcp": _impl.setup_project_codex_mcp,
    "_external_agent_status": _impl._external_agent_status,
    "_run_native_agent": _impl._run_native_agent,
    "_run_validation_commands": _impl._run_validation_commands,
}


def _run_external_agent(*args: Any, **kwargs: Any) -> Any:
    """Compatibility wrapper that keeps example tests patchable via subprocess.run."""

    if "runner" in kwargs or "popen_factory" in kwargs:
        return _impl._run_external_agent(*args, **kwargs)
    prompt = args[0]
    config = args[1]
    command = _impl._build_external_agent_command(config)
    if config.output_last_message_path is not None:
        config.output_last_message_path.parent.mkdir(parents=True, exist_ok=True)
    progress_callback = kwargs.get("progress_callback")
    if progress_callback is not None:
        progress_callback("external_agent_status: running elapsed_seconds=0.0")
    completed = subprocess.run(
        command,
        input=prompt,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=config.timeout_seconds,
        cwd=config.cwd,
    )
    return _external_agent_result_from_completed_process(command, config, completed)


def _run_native_agent(*args: Any, **kwargs: Any) -> Any:
    _sync_patchable_names()
    return _impl._run_native_agent(*args, **kwargs)


def _capability_report(*args: Any, **kwargs: Any) -> Any:
    _sync_patchable_names()
    return _impl._capability_report(*args, **kwargs)


_RUN_EXTERNAL_AGENT_WRAPPER = _run_external_agent
_RUN_NATIVE_AGENT_WRAPPER = _run_native_agent


def main(argv: Any = None) -> int:
    _sync_patchable_names()
    return _impl.main(argv)


def _sync_patchable_names() -> None:
    """Copy compatibility-module monkeypatches into the real implementation."""

    for name, original in _ORIGINALS.items():
        value = globals().get(name, original)
        if name == "_run_native_agent" and value is _RUN_NATIVE_AGENT_WRAPPER:
            value = original
        setattr(_impl, name, value)
    external_agent = globals().get("_run_external_agent", _RUN_EXTERNAL_AGENT_WRAPPER)
    _impl._run_external_agent = external_agent


def __getattr__(name: str) -> Any:
    return getattr(_impl, name)


if __name__ == "__main__":
    raise SystemExit(main())

"""Secret-free native-client authentication checks; never run inference."""

import json
import os
import queue
import subprocess
import threading
from dataclasses import dataclass

from ai_orchestrator import AccessMethod

from ai_provider.external_agents import external_agent_command, run_diagnostic_command


@dataclass(frozen=True)
class AgentReadiness:
    ready: bool
    reason: str
    login_command: tuple[str, ...] = ()


def _copilot_authenticated(command: str, timeout: float) -> bool:
    """Read the official SDK auth.getStatus RPC without creating a session."""

    process = subprocess.Popen(
        (command, "--headless", "--no-auto-update", "--log-level", "none", "--stdio"),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    responses: queue.Queue[bool] = queue.Queue()

    def read() -> None:
        try:
            assert process.stdout is not None
            while True:
                header = process.stdout.readline()
                if not header:
                    break
                if not header.startswith(b"Content-Length:"):
                    continue
                length = int(header.split(b":", 1)[1])
                if not 0 < length <= 1048576:
                    break
                if process.stdout.readline().strip():
                    break
                response = json.loads(process.stdout.read(length))
                if response.get("id") == 1:
                    responses.put(response.get("result", {}).get("isAuthenticated") is True)
                    return
        except (OSError, ValueError, AttributeError):
            pass
        responses.put(False)

    worker = threading.Thread(target=read, daemon=True)
    worker.start()
    try:
        body = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": "auth.getStatus", "params": {}}
        ).encode()
        assert process.stdin is not None
        process.stdin.write(f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
        process.stdin.flush()
        return responses.get(timeout=timeout)
    except (queue.Empty, OSError):
        return False
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        worker.join(timeout=5)
        for stream in (process.stdin, process.stdout):
            if stream is not None:
                stream.close()


def check_agent_readiness(method: AccessMethod, *, timeout: float = 15) -> AgentReadiness:
    """Check authentication without reading tokens or publishing account details."""

    command = external_agent_command(method)
    if command is None:
        return AgentReadiness(False, "official client is not installed/configured")
    if method is AccessMethod.COPILOT_CLI:
        login = (command, "login")
        if any(
            os.getenv(key)
            for key in (
                "COPILOT_PROVIDER_BASE_URL",
                "COPILOT_PROVIDER_API_KEY",
            )
        ):
            return AgentReadiness(False, "Copilot BYOK overrides subscription billing")
        try:
            ready = _copilot_authenticated(command, timeout)
        except OSError:
            ready = False
    elif method is AccessMethod.CODEX_CLI:
        login = (command, "login")
        result = run_diagnostic_command(command, "login", "status", timeout_seconds=timeout)
        ready = result["ok"] and "chatgpt" in (result["stdout"] + result["stderr"]).lower()
    elif method is AccessMethod.KIRO_CLI:
        login = (command, "login")
        result = run_diagnostic_command(
            command, "whoami", "--format", "json", timeout_seconds=timeout
        )
        try:
            identity = json.loads(result["stdout"])
            ready = (
                result["ok"] and isinstance(identity, dict) and bool(identity.get("accountType"))
            )
        except ValueError:
            ready = False
    elif method is AccessMethod.ANTIGRAVITY_CLI:
        login = (command,)
        if os.getenv("GEMINI_API_KEY"):
            return AgentReadiness(False, "Gemini API key may override subscription billing")
        result = run_diagnostic_command(command, "models", timeout_seconds=timeout)
        ready = result["ok"] and bool(result["stdout"])
    else:
        return AgentReadiness(False, "no native authentication check for this access method")
    return AgentReadiness(
        bool(ready), "authenticated" if ready else "sign-in needed or could not be verified", login
    )

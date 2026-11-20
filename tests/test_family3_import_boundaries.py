"""Keep deferred imports from hiding the Family-3 runtime cycles."""

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULES = {
    **{
        f"ai_agent.{name}": ROOT / f"packages/ai_agent/src/ai_agent/{name}.py"
        for name in ("mcp_contracts", "http_proxy", "mcp_server", "ide_bridge", "tool_profiles")
    },
    **{
        f"ai_provider.{name}": ROOT / f"packages/ai_provider/src/ai_provider/{name}.py"
        for name in (
            "acceptance_jobs",
            "acceptance_runtime",
            "acceptance_storage",
            "acceptance_processes",
            "acceptance_harness",
            "acceptance_worker",
        )
    },
}


def test_runtime_import_graph_is_acyclic_including_deferred_imports() -> None:
    graph = {}
    for name, path in MODULES.items():
        graph[name] = {
            node.module
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.ImportFrom) and node.module in MODULES
        }

    def visit(name: str, ancestors: tuple[str, ...]) -> None:
        assert name not in ancestors, " -> ".join((*ancestors, name))
        for dependency in graph[name]:
            visit(dependency, (*ancestors, name))

    for name in graph:
        visit(name, ())


@pytest.mark.parametrize(
    "first,absent,second",
    [
        ("ai_agent.http_proxy", "ai_agent.mcp_server", "ai_agent.mcp_server"),
        ("ai_agent.ide_bridge", "ai_agent.http_proxy", "ai_agent.tool_profiles"),
        (
            "ai_provider.acceptance_runtime",
            "ai_provider.acceptance_jobs",
            "ai_provider.acceptance_jobs",
        ),
    ],
)
def test_lower_layer_import_does_not_load_entry_point(first, absent, second) -> None:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        str(ROOT / f"packages/{package}/src")
        for package in ("ai_agent", "ai_provider", "ai_orchestrator")
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import importlib, sys; importlib.import_module({first!r}); "
            f"assert {absent!r} not in sys.modules; importlib.import_module({second!r})",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_compatibility_exports_keep_contract_identity() -> None:
    from ai_agent import http_proxy, mcp_contracts, mcp_server
    from ai_provider import acceptance_jobs, acceptance_storage

    assert (
        http_proxy.PROTOCOL_VERSION == mcp_server.PROTOCOL_VERSION == mcp_contracts.PROTOCOL_VERSION
    )
    assert http_proxy.validate_loopback_url is mcp_contracts.validate_loopback_url
    for name in (
        "AcceptanceJob",
        "AcceptanceRecord",
        "AcceptanceJobStore",
        "artifact_directory",
        "endpoint",
        "validate_route",
    ):
        assert getattr(acceptance_jobs, name) is getattr(acceptance_storage, name)

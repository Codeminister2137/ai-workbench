"""Bounded, offline health evidence experiment; not a production gate.

Run from the repository root with the existing development Python. Receipts
are exclusive-create, source bytes restored in finally, and no trial retries.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path.cwd()
OUT = ROOT / ".tmp/health-48679817"


def write(name, value):
    with (OUT / name).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(label, command, timeout=300):
    start = time.monotonic()
    with (OUT / f"{label}.log").open("x", encoding="utf-8") as stream:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=suites.test_environment(),
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    receipt = {
        "command": command,
        "exit": result.returncode,
        "seconds": round(time.monotonic() - start, 3),
    }
    write(f"{label}.json", receipt)
    print(label, receipt["exit"], receipt["seconds"], flush=True)
    return receipt


def tests(label, names):
    results = []
    for index, command in enumerate(suites.test_commands(names, ["-q"])):
        xml = OUT / f"{label}-{index}.xml"
        results.append(run(f"{label}-{index}", command + [f"--junitxml={xml}"]))
    cases = {}
    for xml in OUT.glob(f"{label}-*.xml"):
        for case in ET.parse(xml).iter("testcase"):
            key = case.attrib.get("classname", "") + "::" + case.attrib["name"]
            cases[key] = (
                "failed"
                if case.find("failure") is not None or case.find("error") is not None
                else ("skipped" if case.find("skipped") is not None else "passed")
            )
    record = {
        "commands": results,
        "cases": cases,
        "failures": sorted(k for k, v in cases.items() if v == "failed"),
        "seconds": round(sum(r["seconds"] for r in results), 3),
    }
    write(f"{label}.json", record)
    return record


def graph():
    modules = {}
    parsed = {}
    for top in ("apps", "packages", "scripts"):
        for path in sorted((ROOT / top).rglob("*.py")):
            rel = path.relative_to(ROOT)
            if any(
                p.startswith(".") or p in {"__pycache__", "node_modules", "upstream"}
                for p in rel.parts
            ):
                continue
            parts = list(rel.with_suffix("").parts)
            if "src" in parts:
                parts = parts[parts.index("src") + 1 :]
            if parts[-1] == "__init__":
                parts.pop()
            name = ".".join(parts)
            modules[name] = rel.as_posix()
            parsed[name] = ast.parse(path.read_text(encoding="utf-8-sig"))
    edges = {name: set() for name in modules}
    unresolved = []
    for name, tree in parsed.items():
        package = name if modules[name].endswith("__init__.py") else name.rpartition(".")[0]
        for node in ast.walk(tree):
            targets = []
            if isinstance(node, ast.Import):
                targets = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    prefix = package.split(".")[: len(package.split(".")) - node.level + 1]
                    base = ".".join(prefix + ([base] if base else []))
                targets = [base] + [base + "." + a.name for a in node.names]
            for target in targets:
                if target in modules:
                    edges[name].add(target)
                else:
                    unresolved.append([name, node.lineno, target])
    # Tarjan SCCs, including imports in functions and TYPE_CHECKING blocks.
    indices, low, stack, active, components = {}, {}, [], set(), []

    def visit(name):
        indices[name] = low[name] = len(indices)
        stack.append(name)
        active.add(name)
        for target in sorted(edges[name]):
            if target not in indices:
                visit(target)
                low[name] = min(low[name], low[target])
            elif target in active:
                low[name] = min(low[name], indices[target])
        if low[name] == indices[name]:
            component = []
            while True:
                target = stack.pop()
                active.remove(target)
                component.append(target)
                if target == name:
                    break
            if len(component) > 1:
                components.append(sorted(component))

    for name in edges:
        if name not in indices:
            visit(name)
    write(
        "dotted-graph.json",
        {
            "modules": modules,
            "edges": {k: sorted(v) for k, v in edges.items()},
            "sccs": components,
            "unresolved_external_or_alias": unresolved,
            "limitations": "No runtime sys.path aliases/dynamic imports; lexical imports include deferred/type-only edges.",
        },
    )


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=False)
    suites = load("health_suites", "scripts/run-tests.py")
    selector = load("health_selector", "scripts/affected-tests-prototype.py")
    groups = suites.suite_files()
    trials = [
        (
            "source-only",
            "packages/ai_agent/src/ai_agent/workflow_graph.py",
            "_MAX_NODES = 50",
            "_MAX_NODES = 0",
        ),
        (
            "cross-component",
            "packages/ai_orchestrator/src/ai_orchestrator/repair.py",
            'return "no_progress"',
            'return "state_changed"',
        ),
    ]
    write(
        "bounds.json",
        {
            "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
            "trials": trials,
            "deletion": "_PolyglotParser.handle_data",
            "max_test_processes": 18,
            "per_process_timeout_seconds": 300,
            "outer_seconds": 2400,
            "retries": 0,
            "expected_mutation_failures_are_observations": True,
            "stop": "Unexpected baseline/infrastructure failure stops admission; always restore source.",
            "selection_frozen_before_execution": True,
        },
    )
    write("membership.json", groups)
    graph()
    baseline = tests("baseline", ["full"])
    if baseline["failures"] or any(r["exit"] for r in baseline["commands"]):
        raise SystemExit("Baseline failed; inspect logs before admitting mutations")
    for label, relative, old, new in trials:
        path = ROOT / relative
        original = path.read_bytes()
        text = original.decode("utf-8")
        assert text.count(old) == 1
        selection = selector.select_groups([relative], groups)
        write(f"{label}-selection.json", selection)
        try:
            path.write_bytes(text.replace(old, new).encode("utf-8"))
            selected = tests(f"{label}-selected", selection["groups"])
            full = tests(f"{label}-full", ["full"])
            write(
                f"{label}-comparison.json",
                {
                    "full_failures": full["failures"],
                    "selected_failures": selected["failures"],
                    "missed": sorted(set(full["failures"]) - set(selected["failures"])),
                    "selected_cases": len(selected["cases"]),
                    "full_cases": len(full["cases"]),
                    "selected_seconds": selected["seconds"],
                    "full_seconds": full["seconds"],
                    "hash_before": hashlib.sha256(original).hexdigest(),
                    "hash_mutated": hashlib.sha256(path.read_bytes()).hexdigest(),
                },
            )
        finally:
            path.write_bytes(original)
            write(
                f"{label}-restored.json",
                {
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "matches_original": path.read_bytes() == original,
                },
            )
    target = "packages/ai_provider/src/ai_provider/aider_polyglot_scores.py"
    coverage = run(
        "coverage",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_aider_polyglot_scores.py",
            "-q",
            "-n",
            "0",
            "--cov=ai_provider.aider_polyglot_scores",
            "--cov-branch",
            f"--cov-report=json:{OUT / 'coverage-data.json'}",
        ],
        120,
    )
    if coverage["exit"]:
        raise SystemExit("Coverage baseline failed")
    path = ROOT / target
    original = path.read_bytes()
    tree = ast.parse(original)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "_PolyglotParser")
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "handle_data")
    try:
        lines = original.decode("utf-8").splitlines(keepends=True)
        del lines[method.lineno - 1 : method.end_lineno]
        path.write_bytes("".join(lines).encode("utf-8"))
        run(
            "deletion",
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_aider_polyglot_scores.py",
                "-q",
                "-n",
                "0",
            ],
            120,
        )
    finally:
        path.write_bytes(original)
        write(
            "deletion-restored.json",
            {
                "matches_original": path.read_bytes() == original,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            },
        )
    write("finished.json", {"status": "experiments_finished", "not_gate_adoption": True})

"""Family-3 repo health scan: smells / unsustainable design (detector v1).

Cheap structural signals over first-party Python: god modules (lines +
definition counts), long functions (>80 LOC), deep nesting (depth >4),
import cycles (stem-resolved module graph), plus a clone pass via the
repo's own scripts/find-duplication.py (>=15 lines). All signals are
leads, not verdicts: each needs human triage for intent.

Run with --root REPO --output FRESH_RECEIPT.json. Existing receipts are
never replaced. clone_scan preserves subprocess output and exit status;
UNKNOWN/FAILED scans return nonzero and must not be interpreted as clean.
Use this maintained wrapper instead of the historical private detector.py.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path

EXCLUDE_DIRS = {
    ".venv",
    "__pycache__",
    ".tmp",
    ".git",
    "node_modules",
    "upstream",
    "site-packages",
}
INCLUDE_TOPS = ("apps", "packages", "scripts")
LONG_FN_LINES = 80
DEEP_NESTING = 4


def _nesting(node: ast.AST, depth: int = 0) -> int:
    peak = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With)):
            peak = max(peak, _nesting(child, depth + 1))
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        else:
            peak = max(peak, _nesting(child, depth))
    return peak


def scan_file(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
    except (OSError, SyntaxError, UnicodeError):
        return None
    lines = len(text.splitlines())
    fns: list[dict] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            size = (node.end_lineno or node.lineno) - node.lineno + 1
            depth = _nesting(node)
            if size > LONG_FN_LINES or depth > DEEP_NESTING:
                fns.append({"name": node.name, "line": node.lineno, "loc": size, "nest": depth})
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[-1])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[-1])
    return {"lines": lines, "fns": fns, "imports": sorted(imports)}


def find_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    cycles: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    stack: list[str] = []

    def visit(node: str) -> None:
        if node in stack:
            cyc = stack[stack.index(node) :] + [node]
            key = tuple(sorted(set(cyc)))
            if key not in seen:
                seen.add(key)
                cycles.append(cyc)
            return
        stack.append(node)
        for edge in graph.get(node, []):
            if edge in graph:
                visit(edge)
        stack.pop()

    for root in graph:
        visit(root)
    return cycles


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("receipt already exists; choose a fresh output path")
    root = args.root.resolve()
    files: dict[str, dict] = {}
    for top in INCLUDE_TOPS:
        base = root / top
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if any(part in EXCLUDE_DIRS for part in path.relative_to(root).parts):
                continue
            if path.stem.startswith("test_"):
                continue
            info = scan_file(path)
            if info is not None:
                files[path.relative_to(root).as_posix()] = info
    by_size = sorted(files.items(), key=lambda kv: -kv[1]["lines"])[:15]
    long_fns = [{"file": rel, **fn} for rel, info in files.items() for fn in info["fns"]]
    long_fns.sort(key=lambda e: -e["loc"])
    stem_to_files: dict[str, list[str]] = {}
    for rel in files:
        stem_to_files.setdefault(Path(rel).stem, []).append(rel)
    graph: dict[str, list[str]] = {}
    for rel, info in files.items():
        edges: list[str] = []
        for stem in info["imports"]:
            edges.extend(f for f in stem_to_files.get(stem, []) if f != rel)
        graph[rel] = sorted(set(edges))
    cycles = find_cycles(graph)
    clones: list | None = None
    clone_status = "UNKNOWN"
    diagnostic = None
    returncode = None
    stdout = ""
    stderr = ""
    try:
        proc = subprocess.run(
            [
                sys.executable,
                str(root / "scripts" / "find-duplication.py"),
                "--min-lines",
                "15",
                "--json",
                "-",
                *[str(root / top) for top in INCLUDE_TOPS],
            ],
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        returncode, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
        if returncode != 0:
            clone_status = "FAILED"
            diagnostic = f"scanner exited with {returncode}"
        else:
            payload = json.loads(stdout)
            if not isinstance(payload, list) or any(
                not isinstance(group, list)
                or len(group) < 2
                or any(
                    not isinstance(item, dict)
                    or not {"path", "lineno", "name", "key", "nodes", "lines"} <= item.keys()
                    for item in group
                )
                for group in payload
            ):
                raise ValueError("invalid clone group payload")
            clones = payload
            if stderr.strip():
                diagnostic = "scanner reported diagnostics; coverage may be incomplete"
            else:
                clone_status = "COMPLETE"
    except subprocess.TimeoutExpired as exc:
        diagnostic = f"scanner timed out: {exc}"
        stdout = (
            exc.stdout.decode(errors="replace")
            if isinstance(exc.stdout, bytes)
            else exc.stdout or ""
        )
        stderr = (
            exc.stderr.decode(errors="replace")
            if isinstance(exc.stderr, bytes)
            else exc.stderr or ""
        )
        clone_status = "FAILED"
    except OSError as exc:
        diagnostic = f"scanner could not execute: {exc}"
        clone_status = "FAILED"
    except ValueError as exc:
        diagnostic = f"scanner output could not be parsed: {exc}"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as receipt:
        receipt.write(
            json.dumps(
                {
                    "detector": "family3-smells v2",
                    "status": clone_status,
                    "clone_scan": {
                        "status": clone_status,
                        "returncode": returncode,
                        "stdout": stdout,
                        "stderr": stderr,
                        "diagnostic": diagnostic,
                    },
                    "files_scanned": len(files),
                    "largest_files": [
                        {"file": rel, "lines": info["lines"]} for rel, info in by_size
                    ],
                    "long_or_deep_functions": long_fns,
                    "import_cycles": cycles,
                    "clone_groups": clones,
                },
                indent=1,
            )
        )
    print(
        f"scanned {len(files)} files, {len(long_fns)} long/deep fns, "
        f"{len(cycles)} cycles, {len(clones) if isinstance(clones, list) else '?'} clone groups"
    )
    return 0 if clone_status == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())

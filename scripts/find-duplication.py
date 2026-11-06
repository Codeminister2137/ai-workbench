"""Report structurally identical Python functions (duplication scanner).

Walks given paths for *.py, parses each file, and groups function
definitions with identical normalized ASTs. Normalization replaces all
names, arguments, constants, attribute names, and def/class names with
fixed placeholders,
so the groups are type/shape clones (copy-paste with renames), not
semantic clones. Minimum node/line thresholds suppress trivial matches
(small getters all look alike). Findings are leads for centralization,
not verdicts: each group still needs a human to judge whether the
duplication helps (decoupling) or hurts (drift).
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from pathlib import Path


class _Normalizer(ast.NodeTransformer):
    """Replace every identity-bearing leaf with a fixed placeholder."""

    def visit_Name(self, node: ast.Name) -> ast.AST:  # noqa: N802
        return ast.copy_location(ast.Name(id="V", ctx=node.ctx), node)

    def visit_arg(self, node: ast.arg) -> ast.AST:  # noqa: N802
        node.arg = "A"
        return self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> ast.AST:  # noqa: N802
        return ast.copy_location(ast.Constant(value="C"), node)

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:  # noqa: N802
        node.attr = "F"
        return self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:  # noqa: N802
        node.name = "FN"
        return self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:  # noqa: N802
        node.name = "FN"
        return self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:  # noqa: N802
        node.name = "C"
        return self.generic_visit(node)


def signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, int]:
    """Normalized AST dump + node count for one function definition."""
    normalized = _Normalizer().visit(ast.parse(ast.unparse(node)))
    return ast.dump(normalized), sum(1 for _ in ast.walk(node))


def qualified_name(node: ast.AST, parents: dict[int, ast.AST]) -> str:
    """Dotted Class.method / function name from a parent map."""
    parts = []
    current: ast.AST | None = node
    while isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        parts.append(current.name)
        current = parents.get(id(current))
    return ".".join(reversed(parts))


def scan_file(path: Path) -> list[dict]:
    """Parse one file; return per-function records (skips failures loudly)."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeError, OSError) as exc:
        print(f"warning: skipping {path}: {exc}", file=sys.stderr)
        return []
    parents = {id(child): node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    records = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        dump, nodes = signature(node)
        end = getattr(node, "end_lineno", node.lineno) or node.lineno
        records.append(
            {
                "path": str(path),
                "lineno": node.lineno,
                "lines": end - node.lineno + 1,
                "nodes": nodes,
                "name": qualified_name(node, parents),
                "key": hashlib.sha256(dump.encode()).hexdigest()[:16],
            }
        )
    return records


def iter_python_files(roots: list[Path]) -> list[Path]:
    """Collect *.py under roots, skipping hidden dirs and caches."""
    found = []
    for root in roots:
        if root.is_file() and root.suffix == ".py":
            found.append(root)
            continue
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts or any(part.startswith(".") for part in path.parts):
                continue
            found.append(path)
    return found


def find_groups(records: list[dict], *, min_nodes: int, min_lines: int) -> list[list[dict]]:
    """Group records by normalized dump; keep multi-member groups in thresholds."""
    by_key: dict[str, list[dict]] = {}
    for record in records:
        if record["nodes"] < min_nodes or record["lines"] < min_lines:
            continue
        by_key.setdefault(record["key"], []).append(record)
    return sorted(
        (
            sorted(members, key=lambda item: (item["path"], item["lineno"]))
            for members in by_key.values()
            if len(members) > 1
        ),
        key=lambda group: (-len(group), group[0]["path"]),
    )


def format_text(groups: list[list[dict]]) -> str:
    """Render groups as one human-readable block each."""
    chunks = []
    for group in groups:
        head = group[0]
        chunks.append(f"--- {len(group)} clones key={head['key']} nodes={head['nodes']}")
        chunks.extend(f"{item['path']}:{item['lineno']}: {item['name']}" for item in group)
    return "\n".join(chunks)


def main(argv: list[str] | None = None) -> int:
    """Scan paths for duplicated functions; findings never fail the run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--min-nodes", type=int, default=30)
    parser.add_argument("--min-lines", type=int, default=8)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)
    records = []
    for path in iter_python_files(args.paths):
        records.extend(scan_file(path))
    groups = find_groups(records, min_nodes=args.min_nodes, min_lines=args.min_lines)
    print(f"scanned {len(records)} functions, {len(groups)} clone groups")
    if groups:
        print(format_text(groups))
    if args.json is not None:
        args.json.write_text(json.dumps(groups, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

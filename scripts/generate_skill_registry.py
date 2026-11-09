"""Generate docs/skills-registry.md from agent tool definitions.

Usage: python scripts/generate_skill_registry.py [--check]
--check regenerates to a temp file and fails when the committed
registry drifts from tool sources.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages/ai_agent/src"))

from ai_agent.tools.base import BaseTool  # noqa: E402

TOOLS_DIR = ROOT / "packages/ai_agent/src/ai_agent/tools"
OUT_PATH = ROOT / "docs/skills-registry.md"


def _iter_tool_classes() -> list[type]:
    found = []
    for path in sorted(TOOLS_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        module = importlib.import_module(f"ai_agent.tools.{path.stem}")
        for _, obj in sorted(inspect.getmembers(module, inspect.isclass)):
            if (
                issubclass(obj, BaseTool)
                and obj is not BaseTool
                and obj.__module__ == module.__name__
            ):
                found.append(obj)
    return found


def _row_for(cls: type) -> tuple[str, str, str, str, str]:
    try:
        definition = cls().definition  # type: ignore[call-arg]
    except Exception:  # noqa: BLE001 - construction-needing tools recorded plainly
        return (
            cls.__name__,
            "?",
            (cls.__doc__ or "construction requires arguments").strip().splitlines()[0],
            "-",
            cls.__module__,
        )
    params = ", ".join(p.name for p in definition.parameters) or "-"
    return (
        definition.name,
        str(definition.category.value),
        " ".join(definition.description.split()),
        params,
        cls.__module__.rsplit(".", 1)[-1],
    )


def render() -> str:
    lines = [
        "# Skills registry (generated — do not edit by hand)",
        "",
        "Regenerate: `python scripts/generate_skill_registry.py`.",
        "Checked in gate via `--check`.",
        "",
        "| Tool | Category | Description | Parameters | Module |",
        "|---|---|---|---|---|",
    ]
    for cls in _iter_tool_classes():
        name, category, description, params, module = _row_for(cls)
        lines.append(f"| {name} | {category} | {description} | {params} | {module} |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail on drift")
    args = parser.parse_args(argv)
    rendered = render()
    if args.check:
        current = OUT_PATH.read_text(encoding="utf-8") if OUT_PATH.exists() else ""
        if current != rendered:
            with tempfile.NamedTemporaryFile(
                "w", suffix=".md", delete=False, encoding="utf-8"
            ) as handle:
                handle.write(rendered)
                print(f"registry drifted; fresh copy at {handle.name}")
            return 1
        print(f"registry current ({rendered.count(chr(10))} lines)")
        return 0
    OUT_PATH.write_text(rendered, encoding="utf-8")
    print(f"wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

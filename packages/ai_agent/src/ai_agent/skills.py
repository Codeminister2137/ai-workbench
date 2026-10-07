"""Explicit project-local development skills with built-in prerequisite contracts."""

import re
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DevelopmentSkill:
    name: str
    source: Path
    instructions: str
    required_tools: frozenset[str]


@dataclass(frozen=True)
class SkillAvailability:
    name: str
    source: Path | None
    required_tools: tuple[str, ...]
    available: bool
    reason: str | None = None


SKILL_TOOLS = {
    "review-repo-change": frozenset(
        {"git_status", "git_diff", "read_file", "find_files", "grep_search"}
    )
}


def discover_development_skills(
    directories: list[Path], *, available_tools: frozenset[str]
) -> tuple[SkillAvailability, ...]:
    """List supported skill sources and check their tool/runtime prerequisites."""
    results: list[SkillAvailability] = []
    for name, required_tools in sorted(SKILL_TOOLS.items()):
        candidates: set[Path] = set()
        for directory in directories:
            root = directory.resolve()
            candidate = (root / name / "SKILL.md").resolve()
            if not candidate.is_relative_to(root):
                raise ValueError(f"Skill source leaves its configured directory: {name}")
            if candidate.is_file():
                candidates.add(candidate)
        if len(candidates) != 1:
            reason = (
                "no source found"
                if not candidates
                else f"multiple sources found: {len(candidates)}"
            )
            results.append(
                SkillAvailability(name, None, tuple(sorted(required_tools)), False, reason)
            )
            continue

        source = candidates.pop()
        try:
            load_development_skills([name], directories, available_tools=available_tools)
        except (OSError, ValueError) as exc:
            results.append(
                SkillAvailability(name, source, tuple(sorted(required_tools)), False, str(exc))
            )
            continue
        results.append(SkillAvailability(name, source, tuple(sorted(required_tools)), True))
    return tuple(results)


def load_development_skills(
    names: list[str], directories: list[Path], *, available_tools: frozenset[str]
) -> tuple[DevelopmentSkill, ...]:
    """Resolve selected skills only; no installs, tool grants or model inference."""
    selected: list[DevelopmentSkill] = []
    for name in dict.fromkeys(names):
        if name not in SKILL_TOOLS:
            raise ValueError(f"Skill has no supported prerequisite contract: {name}")
        candidates: set[Path] = set()
        for directory in directories:
            root = directory.resolve()
            candidate = (root / name / "SKILL.md").resolve()
            if not candidate.is_relative_to(root):
                raise ValueError(f"Skill source leaves its configured directory: {name}")
            if candidate.is_file():
                candidates.add(candidate)
        if len(candidates) != 1:
            raise ValueError(f"Skill {name} needs exactly one source; found {len(candidates)}")
        source = candidates.pop()
        with source.open(encoding="utf-8") as file:
            instructions = file.read(64_001)
        if len(instructions) > 64_000:
            raise ValueError(f"Skill instructions exceed 64,000 characters: {name}")
        header = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", instructions, re.S)
        declared = re.search(r"^name:\s*([a-z0-9-]+)\s*$", header[1], re.M) if header else None
        if declared is None or declared[1] != name:
            raise ValueError(f"Skill name/frontmatter does not match selection: {name}")
        missing = SKILL_TOOLS[name] - available_tools
        if missing:
            raise ValueError(
                f"Skill {name} requires unavailable tools: {', '.join(sorted(missing))}"
            )
        if any(tool.startswith("git_") for tool in SKILL_TOOLS[name]) and not shutil.which("git"):
            raise ValueError(f"Skill {name} requires an installed Git executable")
        selected.append(DevelopmentSkill(name, source, instructions, SKILL_TOOLS[name]))
    return tuple(selected)


def skill_prompt(skills: tuple[DevelopmentSkill, ...]) -> str:
    """Render identical selected instructions for every eligible execution route."""
    return "\n\n".join(
        f"## Selected development skill: {skill.name}\n"
        "These instructions grant no tools or permissions.\n" + skill.instructions
        for skill in skills
    )

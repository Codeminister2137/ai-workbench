"""Neutral tool selection for explicit coding and research task intents."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolProfilePlan:
    """Expected tool surface and whether external executors can preserve it."""

    name: str
    tool_names: frozenset[str]
    external_executor_supported: bool


def select_tool_profile(
    intent: str, *, delegation: bool = False, discovery: bool = False
) -> ToolProfilePlan:
    """Select a small explicit surface without guessing task intent from prose."""
    if intent == "research":
        return ToolProfilePlan(
            "research",
            frozenset(
                {
                    "fetch_url",
                    "read_research_report",
                    "write_research_report",
                }
            )
            | (frozenset({"search_web"}) if discovery else frozenset()),
            False,
        )
    if intent != "coding":
        raise ValueError(f"Unknown tool profile: {intent}")
    names = {
        "read_file",
        "create_file",
        "edit_file",
        "list_dir",
        "find_files",
        "grep_search",
        "run_command",
    }
    if delegation:
        names.add("delegate_task")
    return ToolProfilePlan("coding", frozenset(names), True)

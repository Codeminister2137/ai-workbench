"""Workflow graphs: named ordered node lists over existing agent runners.

A node is one reusable step: a skill reference, a scrutiny pass, an agent
run (repo-assistant mode + route policy), or an owner-approval checkpoint.
Graphs are stored as JSON and composed in the dashboard list composer;
:func:`plan_graph` dry-maps nodes to their existing runners without
executing anything. There is deliberately no new execution engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

NODE_TYPES = ("skill", "scrutiny", "agent_run", "owner_checkpoint")

# Mirrors repo_assistant_args.CLI_MODES; kept literal so the schema module
# stays import-light (no orchestrator chain).
AGENT_RUN_MODES = ("ask", "review", "implement", "plan", "diagnose", "chat", "coding-chat")

_AGENT_RUN_MODES = AGENT_RUN_MODES

_MAX_NODES = 50
_MAX_TEXT = 2000


def _known_skills() -> frozenset[str]:
    from ai_agent.skills import SKILL_TOOLS

    return frozenset(SKILL_TOOLS)


def _check_text(value: Any, *, field_name: str, required: bool) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Workflow node field {field_name!r} must be a non-empty string")
    if len(value) > _MAX_TEXT:
        raise ValueError(f"Workflow node field {field_name!r} exceeds {_MAX_TEXT} chars")
    return value.strip()


def _check_string_list(value: Any, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"Workflow field {field_name!r} must be a list of strings")
    return tuple(item.strip() for item in value if item.strip())


@dataclass(frozen=True, slots=True)
class WorkflowNode:
    """One step: ``type`` selects the runner, ``config`` carries its arguments."""

    id: str
    type: str
    label: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()

    def validated(self) -> WorkflowNode:
        """Return self when the node shape and type config are sound."""
        node_id = _check_text(self.id, field_name="id", required=True)
        if self.type not in NODE_TYPES:
            raise ValueError(f"Unknown workflow node type: {self.type!r}")
        config = self._validated_config()
        label = self.label.strip()
        if len(label) > _MAX_TEXT:
            raise ValueError("Workflow node label exceeds 2000 chars")
        return WorkflowNode(
            id=node_id,
            type=self.type,
            label=label,
            config=config,
            inputs=tuple(item for item in self.inputs if isinstance(item, str)),
            outputs=tuple(item for item in self.outputs if isinstance(item, str)),
        )

    def _validated_config(self) -> dict[str, Any]:
        if not isinstance(self.config, dict):
            raise ValueError(f"Workflow node {self.id!r} config must be an object")
        if self.type == "skill":
            skill = self.config.get("skill")
            if skill not in _known_skills():
                raise ValueError(f"Workflow node {self.id!r} names unknown skill: {skill!r}")
            return {"skill": skill}
        if self.type == "scrutiny":
            focus = self.config.get("focus", "")
            if focus is not None and not isinstance(focus, str):
                raise ValueError(f"Workflow node {self.id!r} focus must be a string")
            return {"focus": (focus or "").strip()}
        if self.type == "agent_run":
            mode = self.config.get("mode")
            if mode not in _AGENT_RUN_MODES:
                raise ValueError(f"Workflow node {self.id!r} names unknown mode: {mode!r}")
            policy = self.config.get("route_policy", "")
            if policy is not None and not isinstance(policy, str):
                raise ValueError(f"Workflow node {self.id!r} route_policy must be a string")
            return {"mode": mode, "route_policy": (policy or "").strip()}
        question = self.config.get("question")
        return {"question": _check_text(question, field_name="question", required=True)}


@dataclass(frozen=True, slots=True)
class WorkflowGraph:
    """Named ordered node list; execution order is list order."""

    name: str
    nodes: tuple[WorkflowNode, ...] = ()
    description: str = ""

    def validated(self) -> WorkflowGraph:
        name = _check_text(self.name, field_name="name", required=True)
        if len(self.nodes) > _MAX_NODES:
            raise ValueError(f"Workflow exceeds {_MAX_NODES} nodes")
        nodes = tuple(node.validated() for node in self.nodes)
        ids = [node.id for node in nodes]
        if len(set(ids)) != len(ids):
            raise ValueError("Workflow node ids must be unique")
        description = self.description.strip()
        if len(description) > _MAX_TEXT:
            raise ValueError("Workflow description exceeds 2000 chars")
        return WorkflowGraph(name=name, nodes=nodes, description=description)


def node_from_dict(data: Any) -> WorkflowNode:
    """Build a node from plain JSON data, refusing malformed shapes."""
    if not isinstance(data, dict):
        raise ValueError("Workflow node must be an object")
    return WorkflowNode(
        id=data.get("id", ""),
        type=data.get("type", ""),
        label=data.get("label", "") or "",
        config=data.get("config", {}),
        inputs=_check_string_list(data.get("inputs"), field_name="inputs"),
        outputs=_check_string_list(data.get("outputs"), field_name="outputs"),
    ).validated()


def graph_from_dict(data: Any) -> WorkflowGraph:
    """Build a graph from plain JSON data, refusing malformed shapes."""
    if not isinstance(data, dict):
        raise ValueError("Workflow graph must be an object")
    raw_nodes = data.get("nodes", [])
    if not isinstance(raw_nodes, list):
        raise ValueError("Workflow graph nodes must be a list")
    return WorkflowGraph(
        name=data.get("name", ""),
        nodes=tuple(node_from_dict(item) for item in raw_nodes),
        description=data.get("description", "") or "",
    ).validated()


def graph_to_dict(graph: WorkflowGraph) -> dict[str, Any]:
    """Render a graph back to plain JSON data (round-trips from_dict)."""
    graph = graph.validated()
    return {
        "name": graph.name,
        "description": graph.description,
        "nodes": [
            {
                "id": node.id,
                "type": node.type,
                "label": node.label,
                "config": dict(node.config),
                "inputs": list(node.inputs),
                "outputs": list(node.outputs),
            }
            for node in graph.nodes
        ],
    }


def plan_graph(graph: WorkflowGraph) -> list[dict[str, str]]:
    """Dry-map each node to its existing runner; executes nothing.

    The ``runner`` value names the current code path a future executor
    would call (skill loader, scrutiny pass, repo-assistant mode, or the
    owner channel). Unknown references fail in validation, never here.
    """
    graph = graph.validated()
    plan: list[dict[str, str]] = []
    for node in graph.nodes:
        if node.type == "skill":
            runner = f"skill:{node.config['skill']}"
            detail = "load_development_skills + skill_prompt"
        elif node.type == "scrutiny":
            runner = "run_orchestrated_scrutiny"
            detail = node.config["focus"] or "default review pass"
        elif node.type == "agent_run":
            runner = f"repo-assistant:{node.config['mode']}"
            detail = node.config["route_policy"] or "default route policy"
        else:
            runner = "ask_owner"
            detail = node.config["question"]
        plan.append(
            {
                "node_id": node.id,
                "label": node.label or node.type,
                "runner": runner,
                "detail": detail,
            }
        )
    return plan


def cautious_research_template() -> WorkflowGraph:
    """Built-in starting point: plan, implement, two scrutiny passes, owner gate."""
    return WorkflowGraph(
        name="Cautious research loop",
        description="Draft, implement, scrutinize twice, then ask the owner before acting.",
        nodes=(
            WorkflowNode(id="plan", type="agent_run", label="Plan", config={"mode": "plan"}),
            WorkflowNode(
                id="implement",
                type="agent_run",
                label="Implement",
                config={"mode": "implement"},
            ),
            WorkflowNode(
                id="scrutiny-1",
                type="scrutiny",
                label="First scrutiny",
                config={"focus": "correctness and evidence"},
            ),
            WorkflowNode(
                id="scrutiny-2",
                type="scrutiny",
                label="Second scrutiny",
                config={"focus": "risks and scope fit"},
            ),
            WorkflowNode(
                id="owner-gate",
                type="owner_checkpoint",
                label="Owner gate",
                config={"question": "Approve acting on the scrutinized result?"},
            ),
        ),
    ).validated()

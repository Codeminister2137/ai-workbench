"""Workflow graphs: schema validation, dry-run planning, built-in template."""

import pytest
from ai_agent.repo_assistant_args import CLI_MODES
from ai_agent.workflow_graph import (
    AGENT_RUN_MODES,
    WorkflowGraph,
    WorkflowNode,
    cautious_research_template,
    graph_from_dict,
    graph_to_dict,
    plan_graph,
)


def _node(node_id="n1", node_type="skill", **overrides):
    config = {"skill": "git-safety"}
    if node_type == "scrutiny":
        config = {"focus": "risks"}
    elif node_type == "agent_run":
        config = {"mode": "plan", "route_policy": "free_only"}
    elif node_type == "owner_checkpoint":
        config = {"question": "Proceed?"}
    config.update(overrides.pop("config", {}))
    return WorkflowNode(id=node_id, type=node_type, config=config, **overrides)


def test_round_trip_and_plan_mapping() -> None:
    graph = WorkflowGraph(
        name="Demo",
        description="maps every runner",
        nodes=(
            _node("s", "skill", label="Safety", inputs=("repo",), outputs=("notes",)),
            _node("v", "scrutiny"),
            _node("r", "agent_run"),
            _node("g", "owner_checkpoint"),
        ),
    )
    data = graph_to_dict(graph)
    assert graph_from_dict(data) == graph.validated()
    plan = plan_graph(graph)
    assert [step["runner"] for step in plan] == [
        "skill:git-safety",
        "run_orchestrated_scrutiny",
        "repo-assistant:plan",
        "ask_owner",
    ]
    assert plan[2]["detail"] == "free_only"
    assert plan[0]["label"] == "Safety"


def test_rejects_unknown_type_skill_and_mode() -> None:
    with pytest.raises(ValueError, match="Unknown workflow node type"):
        _node("x", "nope").validated()
    with pytest.raises(ValueError, match="unknown skill"):
        _node("x", "skill", config={"skill": "nope"}).validated()
    with pytest.raises(ValueError, match="unknown mode"):
        _node("x", "agent_run", config={"mode": "nope"}).validated()
    with pytest.raises(ValueError, match="question"):
        _node("x", "owner_checkpoint", config={"question": "  "}).validated()


def test_rejects_bad_shapes() -> None:
    with pytest.raises(ValueError, match="must be an object"):
        graph_from_dict([])
    with pytest.raises(ValueError, match="non-empty string"):
        graph_from_dict({"name": "  ", "nodes": []})
    with pytest.raises(ValueError, match="unique"):
        graph_from_dict(
            {
                "name": "dup",
                "nodes": [
                    {"id": "a", "type": "scrutiny", "config": {}},
                    {"id": "a", "type": "scrutiny", "config": {}},
                ],
            }
        )
    with pytest.raises(ValueError, match="exceeds 50 nodes"):
        graph_from_dict(
            {"name": "big", "nodes": [{"id": f"n{i}", "type": "scrutiny"} for i in range(51)]}
        )


def test_run_modes_track_cli_modes() -> None:
    assert AGENT_RUN_MODES == CLI_MODES


def test_template_is_valid_and_ordered() -> None:
    template = cautious_research_template()
    assert [node.type for node in template.nodes].count("scrutiny") == 2
    assert template.nodes[-1].type == "owner_checkpoint"
    assert len(plan_graph(template)) == 5
    assert graph_from_dict(graph_to_dict(template)) == template

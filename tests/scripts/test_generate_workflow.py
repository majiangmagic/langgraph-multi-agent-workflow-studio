"""Tests for the workflow skeleton generator."""

import importlib.util
import json
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "generate_workflow.py"
SPEC = importlib.util.spec_from_file_location("generate_workflow", MODULE_PATH)
generate_workflow = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["generate_workflow"] = generate_workflow
SPEC.loader.exec_module(generate_workflow)


def test_generate_workflow_writes_to_patched_workflows_dir(tmp_path, monkeypatch):
    """Tests must generate into a temp workflows dir, not the real app tree."""

    workflows_dir = tmp_path / "workflows"
    monkeypatch.setattr(generate_workflow, "WORKFLOWS_DIR", workflows_dir)

    dsl_path = tmp_path / "workflow.json"
    dsl_path.write_text(
        json.dumps(
            {
                "version": 1,
                "kind": "workflow",
                "name": "research_pipeline",
                "entrypoint": "planner",
                "nodes": {
                    "planner": {
                        "agent": "official_supervisor",
                        "extension": "supervisor",
                    },
                    "researcher": {
                        "agent": "research_agent",
                        "agent_package": "research/research_agent",
                    },
                    "reviewer": {
                        "agent": "official_supervisor",
                        "state_agent": "review_supervisor",
                        "extension": "supervisor",
                    },
                },
                "edges": [
                    {"from": "planner", "to": "researcher"},
                    {"from": "researcher", "to": "reviewer"},
                    {"from": "reviewer", "to": "END"},
                ],
            }
        ),
        encoding="utf-8",
    )

    assert generate_workflow.main([str(dsl_path)]) == 0
    workflow_dir = workflows_dir / "research_pipeline"

    assert workflow_dir.exists()
    graph_text = (workflow_dir / "graph.py").read_text(encoding="utf-8")
    state_text = (workflow_dir / "state.py").read_text(encoding="utf-8")

    assert not (workflow_dir / "spec.py").exists()
    assert 'WORKFLOW_NAME = "research_pipeline"' in graph_text
    assert "workflow = StateGraph(ResearchPipelineState)" in graph_text
    assert 'workflow.add_node(\n        "planner",' in graph_text
    assert 'create_official_supervisor_graph()' in graph_text
    assert "create_official_supervisor_graph(),," not in graph_text
    assert 'extension=create_supervisor_extension("planner")' in graph_text
    assert 'workflow.add_edge("reviewer", END)' in graph_text
    assert 'workflow.set_entry_point("planner")' in graph_text
    assert (
        "from app.agents.research.research_agent.graph "
        "import create_graph as create_research_research_agent_graph"
    ) in graph_text
    assert "create_research_research_agent_graph()" in graph_text
    assert "ResearchPipelineState = WorkflowState" in state_text
    assert '"planner": "official_supervisor"' in state_text
    assert '"researcher": "research_agent"' in state_text
    assert '"reviewer": "review_supervisor"' in state_text


def test_generate_workflow_rejects_edges_to_missing_nodes(tmp_path, monkeypatch):
    """Invalid graph relations should fail before any app files are written."""

    workflows_dir = tmp_path / "workflows"
    monkeypatch.setattr(generate_workflow, "WORKFLOWS_DIR", workflows_dir)

    dsl_path = tmp_path / "workflow.json"
    dsl_path.write_text(
        json.dumps(
            {
                "kind": "workflow",
                "name": "broken_workflow",
                "entrypoint": "start",
                "nodes": {
                    "start": {"agent": "official_supervisor"},
                },
                "edges": [
                    {"from": "start", "to": "missing"},
                ],
            }
        ),
        encoding="utf-8",
    )

    assert generate_workflow.main([str(dsl_path)]) == 1
    assert not workflows_dir.exists()


def test_generate_workflow_accepts_agent_path_as_package(tmp_path, monkeypatch):
    """A workflow node can use agent: group/name as a shorthand package path."""

    workflows_dir = tmp_path / "workflows"
    monkeypatch.setattr(generate_workflow, "WORKFLOWS_DIR", workflows_dir)

    dsl_path = tmp_path / "workflow.json"
    dsl_path.write_text(
        json.dumps(
            {
                "kind": "workflow",
                "name": "grouped_workflow",
                "entrypoint": "researcher",
                "nodes": {
                    "researcher": {"agent": "research/research_agent"},
                },
                "edges": [{"from": "researcher", "to": "END"}],
            }
        ),
        encoding="utf-8",
    )

    assert generate_workflow.main([str(dsl_path)]) == 0
    graph_text = (workflows_dir / "grouped_workflow" / "graph.py").read_text(
        encoding="utf-8"
    )
    state_text = (workflows_dir / "grouped_workflow" / "state.py").read_text(
        encoding="utf-8"
    )

    assert "from app.agents.research.research_agent.graph import" in graph_text
    assert "create_research_research_agent_graph()" in graph_text
    assert '"researcher": "research_agent"' in state_text

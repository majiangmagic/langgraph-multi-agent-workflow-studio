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
    assert 'name="research_pipeline"' in graph_text
    assert 'entrypoint="planner"' in graph_text
    assert 'name="planner"' in graph_text
    assert 'agent="official_supervisor"' in graph_text
    assert 'state_agent="review_supervisor"' in graph_text
    assert "extension_factory=create_supervisor_extension" in graph_text
    assert 'WorkflowEdgeSpec(source="reviewer", target=END)' in graph_text
    assert "import app.agents.official_supervisor.graph" in graph_text
    assert "import app.agents.research_agent.graph" in graph_text
    assert "ResearchPipelineState = WorkflowState" in state_text
    assert "from app.core.langgraph.workflows.research_pipeline.graph import" in state_text


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

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
    assert "WORKFLOW_METADATA =" in graph_text
    assert "metadata=WORKFLOW_METADATA" in graph_text
    assert (
        "from app.agents.research.research_agent.graph "
        "import create_graph as create_research_research_agent_graph"
    ) in graph_text
    assert "create_research_research_agent_graph()" in graph_text
    assert "ResearchPipelineState = WorkflowState" in state_text
    assert '"planner": "official_supervisor"' in state_text
    assert '"researcher": "research_agent"' in state_text
    assert '"reviewer": "review_supervisor"' in state_text
    assert "workflow_inputs: Optional[Dict[str, Any]] = None" in state_text
    assert "request_context: Optional[Dict[str, Any]] = None" in state_text
    assert "request_context=request_context" in state_text


def test_generate_workflow_normalizes_generic_ui_controls():
    workflow = generate_workflow.parse_workflow_dsl(
        {
            "kind": "workflow",
            "name": "controlled_workflow",
            "nodes": {"worker": {"agent": "worker"}},
            "edges": [{"from": "worker", "to": "END"}],
            "ui": {
                "controls": [
                    {
                        "key": "Prompt Strategy",
                        "type": "segmented",
                        "default": "expressive",
                        "options": [
                            {"value": "expressive", "label": "Expressive"},
                            {"value": "faithful", "label": "Faithful"},
                        ],
                    },
                    {
                        "key": "Creativity",
                        "type": "slider",
                        "default": 0.6,
                        "min": 0,
                        "max": 1,
                        "step": 0.1,
                    },
                    {
                        "key": "Future Control",
                        "type": "future-widget",
                        "default": "custom-value",
                    },
                ]
            },
        }
    )

    control = workflow.ui["controls"][0]
    assert control["key"] == "prompt_strategy"
    assert control["type"] == "segmented"
    assert control["default"] == "expressive"
    slider = workflow.ui["controls"][1]
    assert slider["key"] == "creativity"
    assert slider["type"] == "slider"
    assert slider["default"] == "0.6"
    assert slider["options"] == []
    future = workflow.ui["controls"][2]
    assert future["type"] == "future-widget"
    assert future["default"] == "custom-value"


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


def test_generate_workflow_supports_parallel_fanout_and_join(tmp_path, monkeypatch):
    """List edge endpoints should generate native LangGraph parallel edges."""

    workflows_dir = tmp_path / "workflows"
    monkeypatch.setattr(generate_workflow, "WORKFLOWS_DIR", workflows_dir)
    dsl_path = tmp_path / "parallel.json"
    dsl_path.write_text(
        json.dumps(
            {
                "kind": "workflow",
                "name": "parallel_workflow",
                "entrypoint": "start",
                "nodes": {
                    "start": {"agent": "start_agent"},
                    "left": {"agent": "left_agent"},
                    "right": {"agent": "right_agent"},
                    "join": {
                        "agent": "join_agent",
                        "extension": "pipeline_context",
                    },
                },
                "edges": [
                    {"from": "start", "to": ["left", "right"]},
                    {"from": ["left", "right"], "to": "join"},
                    {"from": "join", "to": "END"},
                ],
            }
        ),
        encoding="utf-8",
    )

    assert generate_workflow.main([str(dsl_path)]) == 0
    graph_text = (workflows_dir / "parallel_workflow" / "graph.py").read_text(
        encoding="utf-8"
    )

    assert 'workflow.add_edge("start", "left")' in graph_text
    assert 'workflow.add_edge("start", "right")' in graph_text
    assert "workflow.add_edge(['left', 'right'], \"join\")" in graph_text
    assert 'extension=create_pipeline_context_extension("join")' in graph_text


def test_generate_workflow_renders_continue_error_policy(tmp_path, monkeypatch):
    workflows_dir = tmp_path / "workflows"
    monkeypatch.setattr(generate_workflow, "WORKFLOWS_DIR", workflows_dir)
    dsl_path = tmp_path / "resilient.json"
    dsl_path.write_text(
        json.dumps(
            {
                "kind": "workflow",
                "name": "resilient_workflow",
                "nodes": {
                    "optional_planner": {
                        "agent": "planner_agent",
                        "on_error": "continue",
                    }
                },
                "edges": [{"from": "optional_planner", "to": "END"}],
            }
        ),
        encoding="utf-8",
    )

    assert generate_workflow.main([str(dsl_path)]) == 0
    graph_text = (workflows_dir / "resilient_workflow" / "graph.py").read_text(
        encoding="utf-8"
    )
    assert "continue_on_error=True" in graph_text
    assert "'on_error': 'continue'" in graph_text


def test_generate_workflow_supports_conditional_bounded_loop(tmp_path, monkeypatch):
    """条件边应生成状态路由，并由状态计数限制循环次数。"""

    workflows_dir = tmp_path / "workflows"
    monkeypatch.setattr(generate_workflow, "WORKFLOWS_DIR", workflows_dir)
    dsl_path = tmp_path / "conditional.json"
    dsl_path.write_text(
        json.dumps(
            {
                "kind": "workflow",
                "name": "repair_workflow",
                "nodes": {
                    "validator": {"agent": "validator"},
                    "repairer": {"agent": "repairer"},
                    "renderer": {"agent": "renderer"},
                },
                "edges": [
                    {
                        "from": "validator",
                        "to": "repairer",
                        "otherwise": "renderer",
                        "condition": {
                            "path": "nodes.validator.needs_repair",
                            "operator": "equals",
                            "value": True,
                        },
                        "loop": {
                            "counter_path": "nodes.repairer.repair_attempts",
                            "max_iterations": 1,
                            "exhausted": "renderer",
                        },
                    },
                    {"from": "repairer", "to": "validator"},
                    {"from": "renderer", "to": "END"},
                ],
            }
        ),
        encoding="utf-8",
    )

    assert generate_workflow.main([str(dsl_path)]) == 0
    graph_text = (workflows_dir / "repair_workflow" / "graph.py").read_text(
        encoding="utf-8"
    )
    assert "create_state_condition_router" in graph_text
    assert "workflow.add_conditional_edges(" in graph_text
    assert "path='nodes.validator.needs_repair'" in graph_text
    assert "counter_path='nodes.repairer.repair_attempts'" in graph_text
    assert "max_iterations=1" in graph_text
    assert "source='validator'" in graph_text
    assert "then_target='repairer'" in graph_text
    assert "otherwise_target='renderer'" in graph_text
    assert '"then": \'repairer\'' in graph_text
    assert '"otherwise": \'renderer\'' in graph_text


def test_generate_workflow_supports_explicit_pipeline_inputs(tmp_path, monkeypatch):
    workflows_dir = tmp_path / "workflows"
    monkeypatch.setattr(generate_workflow, "WORKFLOWS_DIR", workflows_dir)
    dsl_path = tmp_path / "explicit-inputs.json"
    dsl_path.write_text(
        json.dumps(
            {
                "kind": "workflow",
                "name": "explicit_inputs_workflow",
                "nodes": {
                    "source": {"agent": "source_agent"},
                    "consumer": {
                        "agent": "consumer_agent",
                        "extension": "pipeline_context",
                        "inputs": {
                            "scene_document": "source.scene_document",
                            "impact_set": "source.impact_set",
                        },
                    },
                },
                "edges": [
                    {"from": "source", "to": "consumer"},
                    {"from": "consumer", "to": "END"},
                ],
            }
        ),
        encoding="utf-8",
    )

    assert generate_workflow.main([str(dsl_path)]) == 0
    graph_text = (workflows_dir / "explicit_inputs_workflow" / "graph.py").read_text(
        encoding="utf-8"
    )
    assert "inputs={'scene_document': 'source.scene_document', 'impact_set': 'source.impact_set'}" in graph_text
    assert "'inputs': {'scene_document': 'source.scene_document'" in graph_text


def test_generate_workflow_supports_supervisor_conditional_routes(
    tmp_path, monkeypatch
):
    workflows_dir = tmp_path / "workflows"
    monkeypatch.setattr(generate_workflow, "WORKFLOWS_DIR", workflows_dir)
    dsl_path = tmp_path / "supervised.json"
    dsl_path.write_text(
        json.dumps(
            {
                "kind": "workflow",
                "name": "supervised_pipeline",
                "entrypoint": "supervisor",
                "nodes": {
                    "supervisor": {
                        "agent": "official_supervisor",
                        "extension": "supervisor",
                        "config": {
                            "prompt": "Run the declared pipeline.",
                            "max_retries_per_node": 1,
                        },
                    },
                    "editor": {
                        "agent": "editor_agent",
                        "extension": "pipeline_context",
                    },
                    "renderer": {
                        "agent": "renderer_agent",
                        "extension": "pipeline_context",
                        "inputs": {"document": "editor.document"},
                    },
                },
                "edges": [
                    {
                        "from": "supervisor",
                        "to": "editor",
                        "condition": {
                            "path": "nodes.supervisor.next_node",
                            "operator": "equals",
                            "value": "editor",
                        },
                    },
                    {"from": "editor", "to": "supervisor"},
                    {
                        "from": "supervisor",
                        "to": "renderer",
                        "condition": {
                            "path": "nodes.supervisor.next_node",
                            "operator": "equals",
                            "value": "renderer",
                        },
                    },
                    {"from": "renderer", "to": "supervisor"},
                    {
                        "from": "supervisor",
                        "to": "END",
                        "condition": {
                            "path": "nodes.supervisor.next_node",
                            "operator": "equals",
                            "value": "END",
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    assert generate_workflow.main([str(dsl_path)]) == 0
    graph_text = (workflows_dir / "supervised_pipeline" / "graph.py").read_text(
        encoding="utf-8"
    )
    assert "from langgraph.graph import END, StateGraph" in graph_text
    assert "create_workflow_supervisor_graph" in graph_text
    assert "create_react_agent" not in graph_text
    assert "create_handoff_tool" not in graph_text
    assert "handoff_tools" not in graph_text
    assert "workflow = StateGraph(SupervisedPipelineState)" in graph_text
    assert "workflow.add_node(" in graph_text
    assert 'workflow.add_edge("editor", "supervisor")' in graph_text
    assert 'workflow.add_edge("renderer", "supervisor")' in graph_text
    assert "workflow.add_conditional_edges(" in graph_text
    assert "lambda state: state['nodes']['supervisor']['next_node']" in graph_text
    assert "'editor': 'editor'" in graph_text
    assert "'renderer': 'renderer'" in graph_text
    assert "'END': END" in graph_text
    assert "workflow = create_supervisor(" not in graph_text
    assert "create_supervised_workflow(" not in graph_text
    assert "SupervisedWorkerSpec(" not in graph_text
    assert "create_supervised_worker_graph(" not in graph_text
    assert "create_agent_node(" in graph_text
    assert "node_name='supervisor'" in graph_text
    assert "supervisor_worker" not in graph_text
    assert "create_official_supervisor_graph()" not in graph_text
    assert "orchestration" not in graph_text

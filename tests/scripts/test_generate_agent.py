"""Tests for the agent skeleton generator."""

import importlib.util
import json
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "generate_agent.py"
SPEC = importlib.util.spec_from_file_location("generate_agent", MODULE_PATH)
generate_agent = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["generate_agent"] = generate_agent
SPEC.loader.exec_module(generate_agent)

EXAMPLE_AGENTS = MODULE_PATH.parents[1] / "examples" / "agents"


def test_generate_agent_preserves_existing_node_blocks(tmp_path, monkeypatch):
    """Refreshing a DSL should keep business logic for unchanged node names."""

    agents_dir = tmp_path / "agents"
    monkeypatch.setattr(generate_agent, "AGENTS_DIR", agents_dir)

    dsl_path = tmp_path / "agent.json"
    dsl_path.write_text(
        json.dumps(
            {
                "version": 1,
                "kind": "agent",
                "name": "research_agent",
                "config": {
                    "prompt": "Research carefully.",
                    "model": "openai/gpt-4.1",
                    "temperature": 0.2,
                },
                "state": {
                    "query": {"type": "string", "optional": True},
                    "answer": {"type": "string", "optional": True},
                },
                "entrypoint": "search",
                "nodes": {
                    "search": {"handler": "search_node"},
                    "summarize": {"handler": "summarize_node"},
                },
                "edges": [
                    {"from": "search", "to": "summarize"},
                    {"from": "summarize", "to": "END"},
                ],
            }
        ),
        encoding="utf-8",
    )

    assert generate_agent.main([str(dsl_path)]) == 0
    nodes_path = agents_dir / "research_agent" / "nodes.py"
    nodes_text = nodes_path.read_text(encoding="utf-8")
    nodes_path.write_text(
        nodes_text.replace(
            '# <agent-node name="search">',
            '# <agent-node name="search">\n'
            'def normalize_query(value):\n'
            '    return value.strip()\n',
            1,
        ).replace("return {}", "return {'answer': 'kept'}", 1),
        encoding="utf-8",
    )

    assert generate_agent.main([str(dsl_path)]) == 0
    refreshed = nodes_path.read_text(encoding="utf-8")

    assert "return {'answer': 'kept'}" in refreshed
    assert "def normalize_query" in refreshed
    spec_text = (agents_dir / "research_agent" / "spec.py").read_text(
        encoding="utf-8"
    )
    assert "from app.agents.research_agent.nodes import search_node" in spec_text
    assert "return search_node" in spec_text
    assert "节点名 \"search\" 是 DSL 的稳定标识" in refreshed
    assert "prompt" in (
        agents_dir / "research_agent" / "config_defaults.json"
    ).read_text(encoding="utf-8")
    state_text = (agents_dir / "research_agent" / "state.py").read_text(
        encoding="utf-8"
    )
    assert "本轮未经业务拆分的完整用户输入" in state_text
    assert "下游节点应通过 Workflow DSL inputs" in state_text
    assert "request_context: Dict[str, Any]" in state_text


def test_generate_agent_deletes_blocks_missing_from_new_dsl(tmp_path, monkeypatch):
    """If a node is removed from DSL, its generated block is removed too."""

    agents_dir = tmp_path / "agents"
    monkeypatch.setattr(generate_agent, "AGENTS_DIR", agents_dir)
    dsl_path = tmp_path / "agent.json"

    dsl_path.write_text(
        json.dumps(
            {
                "kind": "agent",
                "name": "cleanup_agent",
                "entrypoint": "first",
                "nodes": {
                    "first": {},
                    "second": {},
                },
                "edges": [{"from": "first", "to": "second"}],
            }
        ),
        encoding="utf-8",
    )
    assert generate_agent.main([str(dsl_path)]) == 0
    nodes_path = agents_dir / "cleanup_agent" / "nodes.py"
    nodes_text = nodes_path.read_text(encoding="utf-8")
    nodes_path.write_text(
        nodes_text.replace("return {}", "return {'important': 'delete me'}", 1),
        encoding="utf-8",
    )

    dsl_path.write_text(
        json.dumps(
            {
                "kind": "agent",
                "name": "cleanup_agent",
                "entrypoint": "second",
                "nodes": {
                    "second": {},
                },
                "edges": [{"from": "second", "to": "END"}],
            }
        ),
        encoding="utf-8",
    )

    assert generate_agent.main([str(dsl_path)]) == 0
    refreshed = nodes_path.read_text(encoding="utf-8")

    assert '<agent-node name="first">' not in refreshed
    assert "delete me" not in refreshed
    assert '<agent-node name="second">' in refreshed


def test_generate_agent_supports_grouped_package(tmp_path, monkeypatch):
    """Agent implementations can live under app/agents/<group>/<agent>."""

    agents_dir = tmp_path / "agents"
    monkeypatch.setattr(generate_agent, "AGENTS_DIR", agents_dir)

    dsl_path = tmp_path / "agent.json"
    dsl_path.write_text(
        json.dumps(
            {
                "kind": "agent",
                "name": "research_agent",
                "package": "research/research_agent",
                "entrypoint": "search",
                "nodes": {"search": {"handler": "search_node"}},
                "edges": [{"from": "search", "to": "END"}],
            }
        ),
        encoding="utf-8",
    )

    assert generate_agent.main([str(dsl_path)]) == 0
    agent_dir = agents_dir / "research" / "research_agent"

    assert agent_dir.exists()
    assert (agents_dir / "research" / "__init__.py").exists()
    assert "from app.agents.research.research_agent.spec import" in (
        agent_dir / "graph.py"
    ).read_text(encoding="utf-8")
    assert "from app.agents.research.research_agent.state import" in (
        agent_dir / "nodes.py"
    ).read_text(encoding="utf-8")
    assert '"name": "research_agent"' in (
        agent_dir / "config_defaults.json"
    ).read_text(encoding="utf-8")


def test_prompt_agents_use_real_internal_stages():
    """Complex prompt agents prepare inputs before running business logic."""

    staged_agents = {
        "scene_document_editor": [
            "prepare_context", "prepare_request", "propose_patch", "validate_patch"
        ],
        "scene_document_processor": [
            "prepare_context", "validate_patch", "apply_patch", "validate_document",
            "build_agent_contexts"
        ],
        "character_identity_resolver": [
            "prepare_context", "collect_identities", "resolve_identities", "validate_identity_result"
        ],
        "visual_semantic_resolver": [
            "prepare_context", "prepare_semantics", "resolve_visual_semantics", "validate_visual_result"
        ],
        "prompt_compiler": [
            "prepare_context", "collect_terms", "compile_prompt", "validate_prompt_ir"
        ],
        "prompt_consistency_validator": [
            "prepare_context", "collect_invariants", "validate_prompt", "finalize_validation"
        ],
        "prompt_semantic_repairer": [
            "prepare_context", "collect_repair_scope", "repair_semantics", "validate_repair"
        ],
        "prompt_target_renderer": [
            "prepare_context", "validate_render_input", "render_prompt", "validate_render_result"
        ],
    }
    for agent_name, stages in staged_agents.items():
        data = json.loads(
            (EXAMPLE_AGENTS / f"{agent_name}.json").read_text(encoding="utf-8")
        )
        assert data["entrypoint"] == "prepare_context"
        assert list(data["nodes"]) == stages
        assert data["edges"] == [
            *[
                {"from": source, "to": target}
                for source, target in zip(stages, stages[1:])
            ],
            {"from": stages[-1], "to": "END"},
        ]

    impact_router = json.loads(
        (EXAMPLE_AGENTS / "prompt_impact_router.json").read_text(encoding="utf-8")
    )
    assert set(impact_router["nodes"]) == {"route_impact"}

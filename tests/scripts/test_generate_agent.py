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
        nodes_text.replace("return {}", "return {'answer': 'kept'}", 1),
        encoding="utf-8",
    )

    assert generate_agent.main([str(dsl_path)]) == 0
    refreshed = nodes_path.read_text(encoding="utf-8")

    assert "return {'answer': 'kept'}" in refreshed
    assert "节点名 \"search\" 是 DSL 的稳定标识" in refreshed
    assert "prompt" in (
        agents_dir / "research_agent" / "config_defaults.json"
    ).read_text(encoding="utf-8")


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

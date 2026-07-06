"""Workflow graph for the simple supervisor collaboration pattern."""

from typing import Dict, List

from langgraph.graph import END, StateGraph

import app.agents.supervisor.graph  # noqa: F401
from app.agents.registry import agent_registry
from app.core.langgraph.workflows.adapters.agent import create_agent_node
from app.core.langgraph.workflows.adapters.supervisor import create_supervisor_extension
from app.core.langgraph.workflows.supervisor_simple.state import SupervisorSimpleState
from app.core.langgraph.workflows.registry import workflow_registry


def create_supervisor_simple_graph(
    crew_id: str, agents: List[Dict], system_prompt: str = None
):
    """Create a compiled LangGraph for a simple supervisor agent crew."""

    workflow = StateGraph(SupervisorSimpleState)
    supervisor_graph_factory = agent_registry.get("supervisor")
    if supervisor_graph_factory is None:
        raise ValueError("Agent graph factory 'supervisor' is not registered")
    supervisor_graph = supervisor_graph_factory()

    workflow.add_node(
        "supervisor",
        create_agent_node("supervisor", supervisor_graph, extension=create_supervisor_extension(workflow)),
    )
    workflow.add_edge("supervisor", END)
    workflow.set_entry_point("supervisor")

    return workflow.compile()


workflow_registry.register("supervisor_simple", create_supervisor_simple_graph)

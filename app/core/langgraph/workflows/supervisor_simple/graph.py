"""Workflow graph for the simple supervisor collaboration pattern."""

from typing import Dict, List

from langgraph.graph import END, StateGraph

from app.core.langgraph.workflows.adapters.supervisor import create_supervisor_workflow_node
from app.core.langgraph.workflows.supervisor_simple.state import SupervisorSimpleState
from app.core.langgraph.workflows.registry import workflow_registry


def create_supervisor_simple_graph(
    crew_id: str, agents: List[Dict], system_prompt: str = None
):
    """Create a compiled LangGraph for a simple supervisor agent crew."""

    workflow = StateGraph(SupervisorSimpleState)

    # create_supervisor_workflow_node() is called once while building the graph.
    workflow.add_node("supervisor", create_supervisor_workflow_node(workflow))
    workflow.add_edge("supervisor", END)
    workflow.set_entry_point("supervisor")

    return workflow.compile()


workflow_registry.register("supervisor_simple", create_supervisor_simple_graph)

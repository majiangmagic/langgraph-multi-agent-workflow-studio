"""Workflow graph for the simple supervisor collaboration pattern."""

from typing import Any, Dict, List

from app.agents.official_supervisor.graph import create_official_supervisor_graph
from langgraph.graph import END, StateGraph

from app.core.langgraph.checkpoint import get_checkpointer
from app.core.langgraph.store import get_store
from app.core.langgraph.workflows.adapters.agent import create_agent_node
from app.core.langgraph.workflows.adapters.supervisor import create_supervisor_extension
from app.core.langgraph.workflows.registry import workflow_registry
from app.core.langgraph.workflows.supervisor_simple.state import (
    SupervisorSimpleState,
    build_initial_state,
)

WORKFLOW_NAME = "supervisor_simple"


def create_supervisor_simple_graph(
    crew_id: str,
    agents: List[Dict[str, Any]],
):
    """Create the supervisor workflow with native LangGraph primitives."""

    workflow = StateGraph(SupervisorSimpleState)
    workflow.add_node(
        "supervisor",
        create_agent_node(
            "supervisor",
            create_official_supervisor_graph(),
            extension=create_supervisor_extension("supervisor"),
        ),
    )
    workflow.add_edge("supervisor", END)
    workflow.set_entry_point("supervisor")
    return workflow.compile(checkpointer=get_checkpointer(), store=get_store())


workflow_registry.register(
    WORKFLOW_NAME,
    create_supervisor_simple_graph,
    state_builder=build_initial_state,
)

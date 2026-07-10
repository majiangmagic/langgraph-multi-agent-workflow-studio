"""Workflow graph for the simple supervisor collaboration pattern."""

from typing import Any, Dict, List

import app.agents.official_supervisor.graph  # noqa: F401
from app.core.langgraph.workflows.declarative import compile_workflow_definition
from app.core.langgraph.workflows.registry import workflow_registry
from app.core.langgraph.workflows.supervisor_simple.spec import WORKFLOW_DEFINITION
from app.core.langgraph.workflows.supervisor_simple.state import build_initial_state


def create_supervisor_simple_graph(
    crew_id: str,
    agents: List[Dict[str, Any]],
):
    """Create a compiled LangGraph from the declarative workflow spec."""

    return compile_workflow_definition(WORKFLOW_DEFINITION)


workflow_registry.register(
    WORKFLOW_DEFINITION.name,
    create_supervisor_simple_graph,
    state_builder=build_initial_state,
)

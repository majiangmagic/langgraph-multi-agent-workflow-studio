"""Backward-compatible imports for the supervisor workflow.

New code should import from app.core.langgraph.workflows.orchestrated or
app.agents.supervisor.
"""

from app.core.langgraph.workflows.orchestrated import (
    AgentState,
    OrchestratedAction,
    OrchestratedState,
    build_initial_state,
    create_orchestrated_graph,
)

SupervisorAction = OrchestratedAction
SupervisorState = OrchestratedState
create_supervisor_graph = create_orchestrated_graph

__all__ = [
    "AgentState",
    "SupervisorAction",
    "SupervisorState",
    "build_initial_state",
    "create_supervisor_graph",
]

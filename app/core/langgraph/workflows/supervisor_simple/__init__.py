"""Simple supervisor workflow public API."""

from app.agents.supervisor.state import (
    AgentState,
    SupervisorAction,
)
from app.core.langgraph.workflows.supervisor_simple.state import (
    build_initial_state,
    SupervisorState,
)


def __getattr__(name: str):
    if name == "create_supervisor_simple_graph":
        from app.core.langgraph.workflows.supervisor_simple.graph import (
            create_supervisor_simple_graph,
        )

        return create_supervisor_simple_graph
    raise AttributeError(name)

__all__ = [
    "AgentState",
    "SupervisorAction",
    "SupervisorState",
    "build_initial_state",
    "create_supervisor_simple_graph",
]

"""Official supervisor agent public API."""

from app.agents.official_supervisor.official_runtime import OfficialSupervisorRuntime
from app.agents.official_supervisor.state import (
    DelegatedAgentState,
    SupervisorAction,
    SupervisorState,
)


def __getattr__(name: str):
    if name == "create_graph":
        from app.agents.official_supervisor.graph import create_graph

        return create_graph
    if name == "create_official_supervisor_graph":
        from app.agents.official_supervisor.graph import create_official_supervisor_graph

        return create_official_supervisor_graph
    raise AttributeError(name)


__all__ = [
    "DelegatedAgentState",
    "OfficialSupervisorRuntime",
    "SupervisorAction",
    "SupervisorState",
    "create_graph",
    "create_official_supervisor_graph",
]

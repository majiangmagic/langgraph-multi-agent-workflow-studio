"""Supervisor agent public API."""

from app.agents.base import AgentState
from app.agents.supervisor.agent import SupervisorAgent, supervisor_agent
from app.agents.supervisor.state import (
    SupervisorAction,
    SupervisorState,
)


def __getattr__(name: str):
    if name == "create_supervisor_graph":
        from app.agents.supervisor.graph import create_supervisor_graph

        return create_supervisor_graph
    raise AttributeError(name)


__all__ = [
    "AgentState",
    "SupervisorAction",
    "SupervisorAgent",
    "SupervisorState",
    "create_supervisor_graph",
    "supervisor_agent",
]

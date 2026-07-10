"""Supervisor node backed by the official langgraph-supervisor engine."""

from typing import Dict

from app.agents.supervisor.official_runtime import OfficialSupervisorRuntime
from app.agents.supervisor.state import SupervisorState


class OfficialSupervisorNode:
    """Thin node that lets the official supervisor run inside our shell."""

    def __init__(self, runtime: OfficialSupervisorRuntime | None = None) -> None:
        self.runtime = runtime or OfficialSupervisorRuntime()

    def __call__(self, state: SupervisorState) -> Dict:
        return self.runtime.invoke(state)


official_supervisor = OfficialSupervisorNode()

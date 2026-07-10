"""Node backed by the official langgraph-supervisor engine."""

from typing import Dict

from langchain_core.runnables import RunnableConfig

from app.agents.official_supervisor.official_runtime import OfficialSupervisorRuntime
from app.agents.official_supervisor.state import SupervisorState


class OfficialSupervisorNode:
    """Thin node that lets the official supervisor run inside our shell."""

    def __init__(self, runtime: OfficialSupervisorRuntime | None = None) -> None:
        self.runtime = runtime or OfficialSupervisorRuntime()

    def __call__(
        self,
        state: SupervisorState,
        config: RunnableConfig | None = None,
    ) -> Dict:
        runtime = self.runtime.with_state_config(state)
        return runtime.invoke(state, config=config)


official_supervisor = OfficialSupervisorNode()

"""Generic adapter for running an agent graph as a workflow node."""

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

AgentStatePreparer = Callable[[Dict[str, Any]], Dict[str, Any]]
WorkflowUpdateBuilder = Callable[[Dict[str, Any]], Dict[str, Any]]


@dataclass(frozen=True)
class AgentNodeExtension:
    """Optional extension for agents that need custom workflow integration."""

    prepare_agent_state: AgentStatePreparer
    build_workflow_update: WorkflowUpdateBuilder


def create_agent_node(
    agent_name: str,
    agent_graph: Any,
    extension: Optional[AgentNodeExtension] = None,
):
    """Create a workflow node from a reusable agent graph."""

    def run_agent(state: Dict[str, Any]) -> Dict[str, Any]:
        """Run one agent graph and return only the workflow fields it updates."""

        agent_state = (
            extension.prepare_agent_state(state)
            if extension is not None
            else state[agent_name]
        )
        updated_agent_state = agent_graph.invoke(agent_state)

        if extension is not None:
            return extension.build_workflow_update(updated_agent_state)
        return {agent_name: updated_agent_state}

    return run_agent

"""Generic adapter for running an agent graph as a workflow node."""

from typing import Any, Callable, Dict, Optional

AgentStatePreparer = Callable[[Dict[str, Any]], Dict[str, Any]]
WorkflowUpdateBuilder = Callable[[Dict[str, Any]], Dict[str, Any]]


def create_agent_node(
    agent_name: str,
    agent_graph: Any,
    prepare_agent_state: Optional[AgentStatePreparer] = None,
    build_workflow_update: Optional[WorkflowUpdateBuilder] = None,
):
    """Create a workflow node from a reusable agent graph."""

    def run_agent(state: Dict[str, Any]) -> Dict[str, Any]:
        """Run one agent graph and return only the workflow fields it updates."""

        agent_state = (
            prepare_agent_state(state)
            if prepare_agent_state is not None
            else state[agent_name]
        )
        updated_agent_state = agent_graph.invoke(agent_state)

        if build_workflow_update is not None:
            return build_workflow_update(updated_agent_state)
        return {agent_name: updated_agent_state}

    return run_agent

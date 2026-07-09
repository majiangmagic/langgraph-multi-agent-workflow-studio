"""Workflow adapter for running the reusable supervisor agent."""

from typing import Any, Dict

from langgraph.graph import StateGraph

from app.agents.supervisor.state import DelegatedAgentState, SupervisorState
from app.core.langgraph.workflows.adapters.agent import AgentNodeExtension


def build_workflow_agents(workflow: StateGraph) -> Dict[str, DelegatedAgentState]:
    """Build supervisor-readable agent state from workflow nodes."""

    return {
        agent_name: {
            "agent_id": agent_name,
            "agent_name": agent_name,
            "messages": [],
            "status": "idle",
            "results": None,
            "error": None,
            "tools": [],
        }
        for agent_name in workflow.nodes
    }


def create_supervisor_extension(workflow: StateGraph) -> AgentNodeExtension:
    """Create the optional workflow extension for the supervisor agent."""

    def prepare_supervisor_state(state: Dict[str, Any]) -> SupervisorState:
        """Prepare supervisor state before running the agent graph."""
        agents = state["supervisor"].get("agents")
        if agents is None:
            agents = build_workflow_agents(workflow)
        return {
            **state["supervisor"],
            "agents": agents,
        }

    def build_supervisor_update(
        updated_supervisor_state: SupervisorState,
    ) -> Dict[str, Any]:
        """Write supervisor changes back to workflow state."""
        return {
            "supervisor": updated_supervisor_state,
        }

    return AgentNodeExtension(
        prepare_agent_state=prepare_supervisor_state,
        build_workflow_update=build_supervisor_update,
    )

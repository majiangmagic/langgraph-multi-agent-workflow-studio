"""Workflow adapter for running the reusable supervisor agent."""

from typing import Any, Dict

from app.agents.official_supervisor.state import DelegatedAgentState, SupervisorState
from app.core.langgraph.workflows.adapters.agent import AgentNodeExtension


def build_workflow_agents(
    node_states: Dict[str, Dict[str, Any]],
    supervisor_node: str,
    agent_catalog: Dict[str, Dict[str, Any]] | None = None,
) -> Dict[str, DelegatedAgentState]:
    """Build supervisor-readable agent state from workflow nodes."""

    candidate_states = {
        node_name: node_state
        for node_name, node_state in node_states.items()
        if node_name != supervisor_node
    }
    if not candidate_states and agent_catalog:
        candidate_states = {
            agent_name: agent_state
            for agent_name, agent_state in agent_catalog.items()
            if agent_name != supervisor_node
        }

    return {
        node_name: {
            "agent_id": node_state.get("agent_id", node_name),
            "agent_name": node_state.get("agent_name", node_name),
            "description": node_state.get("description"),
            "system_prompt": node_state.get("system_prompt"),
            "model": node_state.get("model"),
            "temperature": node_state.get("temperature", 0.2),
            "messages": [],
            "status": node_state.get("status", "idle"),
            "results": node_state.get("results"),
            "error": node_state.get("error"),
            "tools": node_state.get("tools", []),
        }
        for node_name, node_state in candidate_states.items()
    }


def create_supervisor_extension(node_name: str) -> AgentNodeExtension:
    """Create the optional workflow extension for the supervisor agent."""

    def prepare_supervisor_state(state: Dict[str, Any]) -> SupervisorState:
        """Prepare supervisor state before running the agent graph."""
        supervisor_state = state["nodes"][node_name]
        agents = supervisor_state.get("agents")
        if not agents:
            agents = build_workflow_agents(
                state["nodes"],
                node_name,
                state.get("agents"),
            )
        return {
            **supervisor_state,
            "agents": agents,
        }

    def build_supervisor_update(
        updated_supervisor_state: SupervisorState,
    ) -> Dict[str, Any]:
        """Write supervisor changes back to workflow state."""
        return {
            "nodes": {
                node_name: updated_supervisor_state,
            },
        }

    return AgentNodeExtension(
        prepare_agent_state=prepare_supervisor_state,
        build_workflow_update=build_supervisor_update,
    )

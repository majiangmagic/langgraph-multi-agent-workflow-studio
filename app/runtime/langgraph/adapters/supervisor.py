"""Workflow adapter for running the reusable supervisor agent."""

from typing import Any, Dict

from app.agents.official_supervisor.state import DelegatedAgentState, SupervisorState
from app.runtime.langgraph.adapters.agent import AgentNodeExtension


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

    runtime_fields = {
        "agent_id",
        "agent_name",
        "description",
        "system_prompt",
        "model",
        "temperature",
        "messages",
        "user_input",
        "workflow_inputs",
        "request_context",
        "status",
        "error",
        "tools",
        "prepared_context",
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
            "results": {
                key: value
                for key, value in node_state.items()
                if key not in runtime_fields and value is not None
            },
            "error": node_state.get("error"),
            "tools": node_state.get("tools", []),
        }
        for node_name, node_state in candidate_states.items()
    }


def create_supervisor_extension(node_name: str) -> AgentNodeExtension:
    """Create the optional workflow extension for the supervisor agent."""

    async def prepare_supervisor_state(state: Dict[str, Any]) -> SupervisorState:
        """Prepare supervisor state before running the agent graph."""
        supervisor_state = state["nodes"][node_name]
        agents = build_workflow_agents(
            state["nodes"],
            node_name,
            state.get("agents"),
        )
        return {
            **supervisor_state,
            "agents": agents,
        }

    async def build_supervisor_update(
        state: Dict[str, Any],
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


def create_supervisor_planner_extension(node_name: str) -> AgentNodeExtension:
    """Run the official supervisor as the planning gate of a fixed DSL graph."""

    async def prepare_supervisor_state(state: Dict[str, Any]) -> SupervisorState:
        supervisor_state = state["nodes"][node_name]
        return {
            **supervisor_state,
            "agents": {},
        }

    async def build_supervisor_update(
        state: Dict[str, Any],
        updated_supervisor_state: SupervisorState,
    ) -> Dict[str, Any]:
        return {"nodes": {node_name: updated_supervisor_state}}

    return AgentNodeExtension(
        prepare_agent_state=prepare_supervisor_state,
        build_workflow_update=build_supervisor_update,
    )

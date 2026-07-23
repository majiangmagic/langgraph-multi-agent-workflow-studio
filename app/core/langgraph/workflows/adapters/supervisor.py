"""Workflow adapter for running the reusable supervisor agent."""

from datetime import UTC, datetime
from typing import Any, Dict
from uuid import uuid4

from langgraph.config import get_store as get_runtime_store

from app.agents.official_supervisor.state import DelegatedAgentState, SupervisorState
from app.core.config import settings
from app.core.langgraph.workflows.adapters.agent import AgentNodeExtension


def memory_namespace(user_id: str) -> tuple[str, ...]:
    """Return the official LangGraph store namespace for one user's memories."""

    return ("memories", user_id)


async def load_supervisor_memories(state: Dict[str, Any]) -> list[Dict[str, Any]]:
    """Load user-scoped long-term memories for the supervisor."""

    if not settings.long_term_memory_enabled:
        return []

    user_id = str(state.get("user_id") or "").strip()
    if not user_id:
        return []

    try:
        store = get_runtime_store()
    except RuntimeError:
        return []

    if store is None:
        return []

    items = await store.asearch(
        memory_namespace(user_id),
        limit=max(settings.long_term_memory_limit, 0),
    )
    return [item.value for item in items]


async def save_supervisor_memory(
    state: Dict[str, Any],
    supervisor_state: SupervisorState,
) -> None:
    """Persist explicit supervisor memory writes to the official store."""

    if not settings.long_term_memory_enabled:
        return

    memory_write = supervisor_state.get("memory_write")
    if not isinstance(memory_write, dict):
        return

    content = str(memory_write.get("content") or "").strip()
    if not content:
        return

    user_id = str(state.get("user_id") or "").strip()
    if not user_id:
        return

    try:
        store = get_runtime_store()
    except RuntimeError:
        return

    if store is None:
        return

    conversation_id = str(state.get("conversation_id") or "")
    key = str(memory_write.get("key") or f"{conversation_id}:supervisor:{uuid4()}")
    await store.aput(
        memory_namespace(user_id),
        key,
        {
            "kind": memory_write.get("kind") or "supervisor_memory",
            "content": content,
            "conversation_id": conversation_id,
            "created_at": datetime.now(UTC).isoformat(),
        },
        index=False,
    )


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
        memories = await load_supervisor_memories(state)
        return {
            **supervisor_state,
            "agents": agents,
            "long_term_memories": memories,
        }

    async def build_supervisor_update(
        state: Dict[str, Any],
        updated_supervisor_state: SupervisorState,
    ) -> Dict[str, Any]:
        """Write supervisor changes back to workflow state."""
        await save_supervisor_memory(state, updated_supervisor_state)
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
        memories = await load_supervisor_memories(state)
        return {
            **supervisor_state,
            "agents": {},
            "long_term_memories": memories,
        }

    async def build_supervisor_update(
        state: Dict[str, Any],
        updated_supervisor_state: SupervisorState,
    ) -> Dict[str, Any]:
        await save_supervisor_memory(state, updated_supervisor_state)
        return {"nodes": {node_name: updated_supervisor_state}}

    return AgentNodeExtension(
        prepare_agent_state=prepare_supervisor_state,
        build_workflow_update=build_supervisor_update,
    )

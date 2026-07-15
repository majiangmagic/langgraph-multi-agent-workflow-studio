"""Shared workflow state helpers."""

from typing import Annotated, Any, Dict, List, Mapping, Optional, TypedDict

from langchain_core.messages import BaseMessage


RESET_NODE_STATE_KEY = "__reset_for_new_turn__"


def normalize_node_name(name: str) -> str:
    """Normalize names used to bind workflow nodes to agent configs."""

    return name.strip().lower().replace(" ", "_")


def merge_node_states(
    current: Optional[Dict[str, Dict[str, Any]]],
    update: Optional[Dict[str, Dict[str, Any]]],
) -> Dict[str, Dict[str, Any]]:
    """Merge node updates into checkpointed workflow state."""

    if not current:
        return {
            node_name: {
                key: value
                for key, value in node_state.items()
                if key != RESET_NODE_STATE_KEY
            }
            for node_name, node_state in (update or {}).items()
        }
    if not update:
        return current

    merged = {**current}
    for node_name, node_update in update.items():
        node_current = current.get(node_name, {})
        reset_for_new_turn = bool(node_update.get(RESET_NODE_STATE_KEY))
        clean_update = {
            key: value
            for key, value in node_update.items()
            if key != RESET_NODE_STATE_KEY
        }
        node_merged = (
            clean_update
            if reset_for_new_turn
            else {**node_current, **clean_update}
        )
        if clean_update.get("messages") == [] and node_current.get("messages"):
            node_merged["messages"] = node_current["messages"]
        merged[node_name] = node_merged
    return merged


class WorkflowState(TypedDict):
    """Generic global workflow state shared by generated workflows."""

    nodes: Annotated[Dict[str, Dict[str, Any]], merge_node_states]
    agents: Dict[str, Dict[str, Any]]
    user_id: str
    crew_id: str
    conversation_id: str
    user_input: Optional[str]
    workflow_inputs: Dict[str, Any]


def build_agent_runtime_state(
    node_name: str,
    agent_config: Dict[str, Any],
    user_input: Optional[str],
    messages: Optional[List[BaseMessage]] = None,
    workflow_inputs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Project a DB agent config into a node-local runtime state."""

    agent_key = agent_config.get("id") or node_name
    return {
        RESET_NODE_STATE_KEY: True,
        "agent_id": str(agent_key),
        "agent_name": agent_config.get("name", node_name),
        "description": agent_config.get("description"),
        "system_prompt": agent_config.get("system_prompt"),
        "model": agent_config.get("model"),
        "temperature": agent_config.get("temperature", 0.2),
        "tools": agent_config.get("tools", []),
        "messages": messages or [],
        "user_input": user_input,
        "workflow_inputs": dict(workflow_inputs or {}),
        "plan": None,
        "action": None,
        "agents": {},
        "status": "idle",
        "results": None,
        "error": None,
    }


def build_workflow_initial_state(
    workflow_name: str,
    node_agents: Mapping[str, str],
    user_id: str,
    crew_id: str,
    agents: List[Dict[str, Any]],
    conversation_id: str = "",
    messages: Optional[List[BaseMessage]] = None,
    user_input: Optional[str] = None,
    workflow_inputs: Optional[Dict[str, Any]] = None,
) -> WorkflowState:
    """Build initial state from workflow node names and agent configs."""

    agents_by_name = {
        normalize_node_name(agent_config["name"]): agent_config
        for agent_config in agents
    }
    agent_catalog = {
        node_name: build_agent_runtime_state(
            node_name=node_name,
            agent_config=agent_config,
            user_input=user_input,
            messages=[],
            workflow_inputs=workflow_inputs,
        )
        for node_name, agent_config in agents_by_name.items()
    }
    node_states = {}
    for node_name, state_agent_name in node_agents.items():
        state_agent_name = normalize_node_name(state_agent_name)
        agent_config = agents_by_name.get(state_agent_name)
        if agent_config is None:
            raise ValueError(
                f"Workflow '{workflow_name}' requires an agent named "
                f"'{state_agent_name}'"
            )
        node_states[node_name] = build_agent_runtime_state(
            node_name=node_name,
            agent_config=agent_config,
            user_input=user_input,
            messages=messages,
            workflow_inputs=workflow_inputs,
        )

    return {
        "nodes": node_states,
        "agents": agent_catalog,
        "user_id": user_id,
        "crew_id": crew_id,
        "conversation_id": conversation_id,
        "user_input": user_input,
        "workflow_inputs": dict(workflow_inputs or {}),
    }

"""Shared state for the simple supervisor workflow."""

import uuid
from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.messages import BaseMessage

from app.agents.supervisor.state import AgentState, SupervisorAction


class SupervisorState(TypedDict):
    """Global state passed through the simple supervisor workflow."""

    messages: List[BaseMessage]
    user_input: Optional[str]
    plan: Optional[Dict[str, Any]]
    agents: Dict[str, AgentState]
    crew_id: str
    conversation_id: str
    action: Optional[SupervisorAction]


def build_initial_state(crew_id: str, agents: List[Dict]) -> SupervisorState:
    """Build the initial global state for a supervisor workflow run."""

    agent_states = {}
    for agent_config in agents:
        agent_id = agent_config.get("id") or str(uuid.uuid4())
        agent_states[agent_id] = {
            "agent_id": agent_id,
            "agent_name": agent_config["name"],
            "messages": [],
            "status": "idle",
            "results": None,
            "tools": agent_config.get("tools", []),
        }

    return {
        "messages": [],
        "user_input": None,
        "plan": None,
        "agents": agent_states,
        "crew_id": crew_id,
        "conversation_id": "",
        "action": None,
    }

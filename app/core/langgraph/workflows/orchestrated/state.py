"""State types for the orchestrated workflow."""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional, TypedDict

from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """State maintained for each agent in the system."""

    agent_id: str
    agent_name: str
    messages: List[BaseMessage]
    status: Literal["idle", "working", "complete", "error"]
    results: Optional[Dict[str, Any]]
    tools: List[Dict[str, Any]]


class OrchestratedAction(str, Enum):
    """Actions that the orchestrated workflow can take."""

    ANSWER_DIRECTLY = "answer_directly"
    CREATE_PLAN = "create_plan"
    ASSIGN_TASKS = "assign_tasks"
    CHECK_STATUS = "check_status"
    COMBINE_RESULTS = "combine_results"


class OrchestratedState(TypedDict):
    """Shared state passed through the orchestrated workflow."""

    messages: List[BaseMessage]
    user_input: Optional[str]
    plan: Optional[Dict[str, Any]]
    agents: Dict[str, AgentState]
    crew_id: str
    conversation_id: str
    action: Optional[OrchestratedAction]

"""State and action types owned by the supervisor agent."""

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


class SupervisorAction(str, Enum):
    """Actions that the supervisor agent can request."""

    ANSWER_DIRECTLY = "answer_directly"
    CREATE_PLAN = "create_plan"
    ASSIGN_TASKS = "assign_tasks"
    CHECK_STATUS = "check_status"
    COMBINE_RESULTS = "combine_results"

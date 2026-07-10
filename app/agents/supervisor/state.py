"""State and action types owned by the supervisor agent."""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional, TypedDict

from langchain_core.messages import BaseMessage


class SupervisorAction(str, Enum):
    """Actions that the supervisor agent can request."""

    ANSWER_DIRECTLY = "answer_directly"
    CREATE_PLAN = "create_plan"
    ASSIGN_TASKS = "assign_tasks"
    CHECK_STATUS = "check_status"
    COMBINE_RESULTS = "combine_results"


class DelegatedAgentState(TypedDict):
    """Task-level state tracked by the supervisor for a delegated agent."""

    agent_id: str
    agent_name: str
    description: Optional[str]
    system_prompt: Optional[str]
    model: Optional[str]
    temperature: float
    messages: List[BaseMessage]
    status: Literal["idle", "working", "complete", "error"]
    results: Optional[Dict[str, Any]]
    error: Optional[str]
    tools: List[Dict[str, Any]]


class SupervisorState(TypedDict):
    """State owned by the supervisor agent within a workflow run."""

    messages: List[BaseMessage]
    user_input: Optional[str]
    plan: Optional[Dict[str, Any]]
    action: Optional[SupervisorAction]
    agents: Dict[str, DelegatedAgentState]

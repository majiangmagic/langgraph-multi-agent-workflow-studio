"""State and action types owned by the official supervisor agent."""

from enum import Enum
from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict

from langgraph.managed import RemainingSteps
from typing_extensions import NotRequired

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


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
    """Runtime state for an agent running the supervisor implementation."""

    agent_id: str
    agent_name: str
    description: Optional[str]
    system_prompt: Optional[str]
    model: Optional[str]
    temperature: float
    tools: List[Dict[str, Any]]
    messages: Annotated[List[BaseMessage], add_messages]
    # 本轮未经业务拆分的完整用户输入。监管者需要据此规划流程；普通下游 Agent
    # 理论上不应直接使用，而应通过 Workflow DSL inputs 接收结构化业务数据。
    user_input: Optional[str]
    workflow_inputs: Dict[str, Any]
    # 由平台统一注入的请求标识、会话标识和用户标识，不属于用户可配置参数。
    request_context: Dict[str, Any]
    plan: Optional[Dict[str, Any]]
    action: Optional[SupervisorAction]
    agents: Dict[str, DelegatedAgentState]
    next_node: NotRequired[str]
    long_term_memories: NotRequired[List[Dict[str, Any]]]
    remaining_steps: NotRequired[RemainingSteps]

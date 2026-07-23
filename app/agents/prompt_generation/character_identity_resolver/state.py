"""State schema for the character_identity_resolver agent."""

from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.messages import BaseMessage


class CharacterIdentityResolverState(TypedDict):
    """Runtime state for this generated agent."""

    agent_id: str
    agent_name: str
    description: Optional[str]
    system_prompt: Optional[str]
    model: Optional[str]
    temperature: float
    tools: List[Dict[str, Any]]
    messages: List[BaseMessage]
    # 本轮未经业务拆分的完整用户输入。除入口或意图解析节点外，理论上不应直接使用；
    # 下游节点应通过 Workflow DSL inputs 接收上游节点产出的结构化业务数据。
    user_input: Optional[str]
    workflow_inputs: Dict[str, Any]
    # 由平台统一注入的请求标识、会话标识和用户标识，不属于用户可配置参数。
    request_context: Dict[str, Any]

    # 下面是 DSL 声明的业务状态字段。
    identity_context: Optional[Dict[str, Any]]
    previous_resolved_prompt_ir: Optional[Dict[str, Any]]
    impact_set: Optional[Dict[str, Any]]
    identity_terms: Optional[List[Any]]
    identity_tag_records: Optional[List[Any]]
    identity_tag_resolutions: Optional[List[Any]]
    identity_tag_adjudication: Optional[Dict[str, Any]]
    identity_search_terms: Optional[List[Any]]
    prepared_context: Optional[Dict[str, Any]]

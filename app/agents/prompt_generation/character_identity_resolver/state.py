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
    user_input: Optional[str]
    workflow_inputs: Dict[str, Any]

    # 下面是 DSL 声明的业务状态字段。
    scene_document: Optional[Dict[str, Any]]
    previous_resolved_prompt_ir: Optional[Dict[str, Any]]
    impact_set: Optional[Dict[str, Any]]
    identity_terms: Optional[List[Any]]
    identity_tag_records: Optional[List[Any]]
    identity_tag_resolutions: Optional[List[Any]]
    identity_tag_adjudication: Optional[Dict[str, Any]]
    identity_search_terms: Optional[List[Any]]

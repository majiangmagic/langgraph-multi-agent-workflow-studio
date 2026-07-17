"""State schema for the prompt_compiler agent."""

from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.messages import BaseMessage


class PromptCompilerState(TypedDict):
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
    atomic_terms: Optional[List[Any]]
    relation_terms: Optional[List[Any]]
    negative_terms: Optional[List[Any]]
    identity_tag_records: Optional[List[Any]]
    identity_tag_resolutions: Optional[List[Any]]
    identity_tag_adjudication: Optional[Dict[str, Any]]
    visual_tag_records: Optional[List[Any]]
    visual_tag_resolutions: Optional[List[Any]]
    visual_tag_adjudication: Optional[Dict[str, Any]]
    repair_overlay: Optional[Dict[str, Any]]
    resolved_prompt_ir: Optional[Dict[str, Any]]
    draft_prompt: Optional[str]
    negative_prompt: Optional[str]

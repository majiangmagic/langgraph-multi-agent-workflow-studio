"""State schema for the scene_document_processor agent."""

from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.messages import BaseMessage


class SceneDocumentProcessorState(TypedDict):
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
    previous_scene_document: Optional[Dict[str, Any]]
    previous_resolved_prompt_ir: Optional[Dict[str, Any]]
    patch_proposal: Optional[Dict[str, Any]]
    impact_set: Optional[Dict[str, Any]]
    patch_error: Optional[str]
    clarification_request: Optional[str]
    document_valid: Optional[bool]

"""State helpers for the prompt_generation_workflow workflow."""

from typing import Any, Dict, List, Optional

from langchain_core.messages import BaseMessage

from app.core.langgraph.workflows.declarative import (
    WorkflowState,
    build_workflow_initial_state,
    merge_node_states,
)

PromptGenerationWorkflowState = WorkflowState

WORKFLOW_NAME = "prompt_generation_workflow"
NODE_AGENTS = {
    "scene_document_editor": "scene_document_editor",
    "scene_document_processor": "scene_document_processor",
    "identity_impact_router": "prompt_impact_router",
    "character_identity_resolver": "character_identity_resolver",
    "visual_impact_router": "prompt_impact_router",
    "visual_semantic_resolver": "visual_semantic_resolver",
    "prompt_compiler": "prompt_compiler",
    "consistency_validator": "prompt_consistency_validator",
    "semantic_repairer": "prompt_semantic_repairer",
    "target_renderer": "prompt_target_renderer",
}


def build_initial_state(
    crew_id: str,
    agents: List[Dict[str, Any]],
    user_id: str = "",
    conversation_id: str = "",
    messages: Optional[List[BaseMessage]] = None,
    user_input: Optional[str] = None,
    workflow_inputs: Optional[Dict[str, Any]] = None,
) -> WorkflowState:
    """Build initial state for this workflow definition."""

    return build_workflow_initial_state(
        workflow_name=WORKFLOW_NAME,
        node_agents=NODE_AGENTS,
        user_id=user_id,
        crew_id=crew_id,
        agents=agents,
        conversation_id=conversation_id,
        messages=messages,
        user_input=user_input,
        workflow_inputs=workflow_inputs,
    )

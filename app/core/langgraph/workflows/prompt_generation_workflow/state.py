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
    "supervisor": "official_supervisor",
    "requirement_analyzer": "prompt_requirement_analyzer",
    "danbooru_query": "prompt_danbooru_query",
    "prompt_writer": "prompt_writer",
    "prompt_reviewer": "prompt_reviewer",
    "format_converter": "prompt_format_converter",
}


def build_initial_state(
    crew_id: str,
    agents: List[Dict[str, Any]],
    user_id: str = "",
    conversation_id: str = "",
    messages: Optional[List[BaseMessage]] = None,
    user_input: Optional[str] = None,
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
    )

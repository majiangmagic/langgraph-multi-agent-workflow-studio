"""Public API for the prompt_generation_workflow workflow."""

from app.core.langgraph.workflows.prompt_generation_workflow.state import (
    PromptGenerationWorkflowState,
    build_initial_state,
)


def __getattr__(name: str):
    if name == "create_prompt_generation_workflow_graph":
        from app.core.langgraph.workflows.prompt_generation_workflow.graph import create_prompt_generation_workflow_graph

        return create_prompt_generation_workflow_graph
    raise AttributeError(name)


__all__ = [
    "PromptGenerationWorkflowState",
    "build_initial_state",
    "create_prompt_generation_workflow_graph",
]

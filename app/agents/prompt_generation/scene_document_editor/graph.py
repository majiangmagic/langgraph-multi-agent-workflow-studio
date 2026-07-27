"""Graph factory for the scene_document_editor agent."""

from app.runtime.langgraph.agent_definition import compile_agent_definition
from app.agents.prompt_generation.scene_document_editor.spec import AGENT_DEFINITION, SCENE_DOCUMENT_EDITOR_AGENT_NAME
from app.agents.registry import agent_registry


def create_graph():
    """Create the scene_document_editor agent graph."""

    return compile_agent_definition(AGENT_DEFINITION)


agent_registry.register(SCENE_DOCUMENT_EDITOR_AGENT_NAME, create_graph)

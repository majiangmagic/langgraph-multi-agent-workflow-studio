"""Graph factory for the prompt_target_renderer agent."""

from app.runtime.langgraph.agent_definition import compile_agent_definition
from app.agents.prompt_generation.prompt_target_renderer.spec import AGENT_DEFINITION, PROMPT_TARGET_RENDERER_AGENT_NAME
from app.agents.registry import agent_registry


def create_graph():
    """Create the prompt_target_renderer agent graph."""

    return compile_agent_definition(AGENT_DEFINITION)


agent_registry.register(PROMPT_TARGET_RENDERER_AGENT_NAME, create_graph)

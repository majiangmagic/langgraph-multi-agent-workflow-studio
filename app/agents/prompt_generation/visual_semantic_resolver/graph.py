"""Graph factory for the visual_semantic_resolver agent."""

from app.runtime.langgraph.agent_definition import compile_agent_definition
from app.agents.prompt_generation.visual_semantic_resolver.spec import AGENT_DEFINITION, VISUAL_SEMANTIC_RESOLVER_AGENT_NAME
from app.agents.registry import agent_registry


def create_graph():
    """Create the visual_semantic_resolver agent graph."""

    return compile_agent_definition(AGENT_DEFINITION)


agent_registry.register(VISUAL_SEMANTIC_RESOLVER_AGENT_NAME, create_graph)

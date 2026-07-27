"""Graph factory for the character_identity_resolver agent."""

from app.runtime.langgraph.agent_definition import compile_agent_definition
from app.agents.prompt_generation.character_identity_resolver.spec import AGENT_DEFINITION, CHARACTER_IDENTITY_RESOLVER_AGENT_NAME
from app.agents.registry import agent_registry


def create_graph():
    """Create the character_identity_resolver agent graph."""

    return compile_agent_definition(AGENT_DEFINITION)


agent_registry.register(CHARACTER_IDENTITY_RESOLVER_AGENT_NAME, create_graph)

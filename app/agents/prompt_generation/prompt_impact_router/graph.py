"""Graph factory for the prompt_impact_router agent."""

from app.agents.declarative import compile_agent_definition
from app.agents.prompt_generation.prompt_impact_router.spec import AGENT_DEFINITION, PROMPT_IMPACT_ROUTER_AGENT_NAME
from app.agents.registry import agent_registry


def create_graph():
    """Create the prompt_impact_router agent graph."""

    return compile_agent_definition(AGENT_DEFINITION)


agent_registry.register(PROMPT_IMPACT_ROUTER_AGENT_NAME, create_graph)

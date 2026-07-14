"""Graph factory for the prompt_reviewer agent."""

from app.agents.declarative import compile_agent_definition
from app.agents.prompt_generation.prompt_reviewer.spec import AGENT_DEFINITION, PROMPT_REVIEWER_AGENT_NAME
from app.agents.registry import agent_registry


def create_graph():
    """Create the prompt_reviewer agent graph."""

    return compile_agent_definition(AGENT_DEFINITION)


agent_registry.register(PROMPT_REVIEWER_AGENT_NAME, create_graph)

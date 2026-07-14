"""Graph factory for the prompt_danbooru_query agent."""

from app.agents.declarative import compile_agent_definition
from app.agents.prompt_generation.danbooru_query.spec import AGENT_DEFINITION, PROMPT_DANBOORU_QUERY_AGENT_NAME
from app.agents.registry import agent_registry


def create_graph():
    """Create the prompt_danbooru_query agent graph."""

    return compile_agent_definition(AGENT_DEFINITION)


agent_registry.register(PROMPT_DANBOORU_QUERY_AGENT_NAME, create_graph)

"""Graph factory for the prompt_format_converter agent."""

from app.agents.declarative import compile_agent_definition
from app.agents.prompt_generation.format_converter.spec import AGENT_DEFINITION, PROMPT_FORMAT_CONVERTER_AGENT_NAME
from app.agents.registry import agent_registry


def create_graph():
    """Create the prompt_format_converter agent graph."""

    return compile_agent_definition(AGENT_DEFINITION)


agent_registry.register(PROMPT_FORMAT_CONVERTER_AGENT_NAME, create_graph)

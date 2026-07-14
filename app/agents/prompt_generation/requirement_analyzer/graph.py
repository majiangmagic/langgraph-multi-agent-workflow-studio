"""Graph factory for the prompt_requirement_analyzer agent."""

from app.agents.declarative import compile_agent_definition
from app.agents.prompt_generation.requirement_analyzer.spec import AGENT_DEFINITION, PROMPT_REQUIREMENT_ANALYZER_AGENT_NAME
from app.agents.registry import agent_registry


def create_graph():
    """Create the prompt_requirement_analyzer agent graph."""

    return compile_agent_definition(AGENT_DEFINITION)


agent_registry.register(PROMPT_REQUIREMENT_ANALYZER_AGENT_NAME, create_graph)

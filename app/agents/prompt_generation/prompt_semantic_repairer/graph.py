"""Graph factory for the prompt_semantic_repairer agent."""

from app.runtime.langgraph.agent_definition import compile_agent_definition
from app.agents.prompt_generation.prompt_semantic_repairer.spec import AGENT_DEFINITION, PROMPT_SEMANTIC_REPAIRER_AGENT_NAME
from app.agents.registry import agent_registry


def create_graph():
    """Create the prompt_semantic_repairer agent graph."""

    return compile_agent_definition(AGENT_DEFINITION)


agent_registry.register(PROMPT_SEMANTIC_REPAIRER_AGENT_NAME, create_graph)

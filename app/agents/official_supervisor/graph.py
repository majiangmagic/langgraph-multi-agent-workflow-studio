"""Graph factory for the official supervisor agent."""

from app.agents.declarative import compile_agent_definition
from app.agents.official_supervisor.spec import (
    AGENT_DEFINITION,
    OFFICIAL_SUPERVISOR_AGENT_NAME,
)
from app.agents.registry import agent_registry


def create_graph(
    system_prompt: str | None = None,
    model_name: str | None = None,
    temperature: float = 0.2,
):
    """Create the official supervisor agent graph."""

    return compile_agent_definition(AGENT_DEFINITION)


create_official_supervisor_graph = create_graph

agent_registry.register(OFFICIAL_SUPERVISOR_AGENT_NAME, create_graph)

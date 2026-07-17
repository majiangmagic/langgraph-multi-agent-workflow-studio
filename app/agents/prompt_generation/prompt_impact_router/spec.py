"""Declarative spec for the prompt_impact_router agent."""

from langgraph.graph import END

from app.agents.declarative import AgentDefinition, AgentEdgeSpec, AgentNodeSpec
from app.agents.prompt_generation.prompt_impact_router.nodes import route_impact_node
from app.agents.prompt_generation.prompt_impact_router.state import PromptImpactRouterState

PROMPT_IMPACT_ROUTER_AGENT_NAME = "prompt_impact_router"
PROMPT_IMPACT_ROUTER_ENTRYPOINT = "route_impact"


def create_route_impact_node():
    """Create the route_impact node callable."""

    return route_impact_node


AGENT_DEFINITION = AgentDefinition(
    name=PROMPT_IMPACT_ROUTER_AGENT_NAME,
    state_schema=PromptImpactRouterState,
    entrypoint=PROMPT_IMPACT_ROUTER_ENTRYPOINT,
    nodes=[
        AgentNodeSpec(
            name="route_impact",
            factory=create_route_impact_node,
        ),
    ],
    edges=[
        AgentEdgeSpec(source="route_impact", target=END),
    ],
)

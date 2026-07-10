"""Declarative spec for the official supervisor agent."""

from langgraph.graph import END

from app.agents.declarative import AgentDefinition, AgentEdgeSpec, AgentNodeSpec
from app.agents.official_supervisor.nodes import OfficialSupervisorNode
from app.agents.official_supervisor.official_runtime import OfficialSupervisorRuntime
from app.agents.official_supervisor.state import SupervisorState

OFFICIAL_SUPERVISOR_AGENT_NAME = "official_supervisor"
OFFICIAL_SUPERVISOR_NODE_NAME = "official_supervisor"


def create_official_supervisor_node() -> OfficialSupervisorNode:
    """Create the runtime node for the official supervisor engine."""

    return OfficialSupervisorNode(OfficialSupervisorRuntime())


AGENT_DEFINITION = AgentDefinition(
    name=OFFICIAL_SUPERVISOR_AGENT_NAME,
    state_schema=SupervisorState,
    entrypoint=OFFICIAL_SUPERVISOR_NODE_NAME,
    nodes=[
        AgentNodeSpec(
            name=OFFICIAL_SUPERVISOR_NODE_NAME,
            factory=create_official_supervisor_node,
        ),
    ],
    edges=[
        AgentEdgeSpec(source=OFFICIAL_SUPERVISOR_NODE_NAME, target=END),
    ],
)

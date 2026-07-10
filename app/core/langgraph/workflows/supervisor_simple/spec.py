"""Declarative spec for the simple supervisor workflow."""

from langgraph.graph import END

from app.agents.official_supervisor.spec import OFFICIAL_SUPERVISOR_AGENT_NAME
from app.core.langgraph.workflows.adapters.supervisor import create_supervisor_extension
from app.core.langgraph.workflows.declarative import (
    WorkflowDefinition,
    WorkflowEdgeSpec,
    WorkflowNodeSpec,
)

SUPERVISOR_NODE_NAME = "supervisor"

WORKFLOW_DEFINITION = WorkflowDefinition(
    name="supervisor_simple",
    entrypoint=SUPERVISOR_NODE_NAME,
    nodes=[
        WorkflowNodeSpec(
            name=SUPERVISOR_NODE_NAME,
            agent=OFFICIAL_SUPERVISOR_AGENT_NAME,
            extension_factory=create_supervisor_extension,
        ),
    ],
    edges=[
        WorkflowEdgeSpec(source=SUPERVISOR_NODE_NAME, target=END),
    ],
)

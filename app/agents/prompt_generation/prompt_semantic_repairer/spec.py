"""Declarative spec for the prompt_semantic_repairer agent."""

from langgraph.graph import END

from app.runtime.langgraph.agent_definition import AgentDefinition, AgentEdgeSpec, AgentNodeSpec
from app.agents.prompt_generation.prompt_semantic_repairer.nodes import prepare_context_node, collect_repair_scope_node, repair_semantics_node, validate_repair_node
from app.agents.prompt_generation.prompt_semantic_repairer.state import PromptSemanticRepairerState

PROMPT_SEMANTIC_REPAIRER_AGENT_NAME = "prompt_semantic_repairer"
PROMPT_SEMANTIC_REPAIRER_ENTRYPOINT = "prepare_context"


def create_prepare_context_node():
    """Create the prepare_context node callable."""

    return prepare_context_node


def create_collect_repair_scope_node():
    """Create the collect_repair_scope node callable."""

    return collect_repair_scope_node


def create_repair_semantics_node():
    """Create the repair_semantics node callable."""

    return repair_semantics_node


def create_validate_repair_node():
    """Create the validate_repair node callable."""

    return validate_repair_node


AGENT_DEFINITION = AgentDefinition(
    name=PROMPT_SEMANTIC_REPAIRER_AGENT_NAME,
    state_schema=PromptSemanticRepairerState,
    entrypoint=PROMPT_SEMANTIC_REPAIRER_ENTRYPOINT,
    nodes=[
        AgentNodeSpec(
            name="prepare_context",
            factory=create_prepare_context_node,
        ),
        AgentNodeSpec(
            name="collect_repair_scope",
            factory=create_collect_repair_scope_node,
        ),
        AgentNodeSpec(
            name="repair_semantics",
            factory=create_repair_semantics_node,
        ),
        AgentNodeSpec(
            name="validate_repair",
            factory=create_validate_repair_node,
        ),
    ],
    edges=[
        AgentEdgeSpec(source="prepare_context", target='collect_repair_scope'),
        AgentEdgeSpec(source="collect_repair_scope", target='repair_semantics'),
        AgentEdgeSpec(source="repair_semantics", target='validate_repair'),
        AgentEdgeSpec(source="validate_repair", target=END),
    ],
)

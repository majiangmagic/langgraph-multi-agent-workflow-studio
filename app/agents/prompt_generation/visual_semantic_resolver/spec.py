"""Declarative spec for the visual_semantic_resolver agent."""

from langgraph.graph import END

from app.runtime.langgraph.agent_definition import AgentDefinition, AgentEdgeSpec, AgentNodeSpec
from app.agents.prompt_generation.visual_semantic_resolver.nodes import prepare_context_node, prepare_semantics_node, resolve_visual_semantics_node, validate_visual_result_node
from app.agents.prompt_generation.visual_semantic_resolver.state import VisualSemanticResolverState

VISUAL_SEMANTIC_RESOLVER_AGENT_NAME = "visual_semantic_resolver"
VISUAL_SEMANTIC_RESOLVER_ENTRYPOINT = "prepare_context"


def create_prepare_context_node():
    """Create the prepare_context node callable."""

    return prepare_context_node


def create_prepare_semantics_node():
    """Create the prepare_semantics node callable."""

    return prepare_semantics_node


def create_resolve_visual_semantics_node():
    """Create the resolve_visual_semantics node callable."""

    return resolve_visual_semantics_node


def create_validate_visual_result_node():
    """Create the validate_visual_result node callable."""

    return validate_visual_result_node


AGENT_DEFINITION = AgentDefinition(
    name=VISUAL_SEMANTIC_RESOLVER_AGENT_NAME,
    state_schema=VisualSemanticResolverState,
    entrypoint=VISUAL_SEMANTIC_RESOLVER_ENTRYPOINT,
    nodes=[
        AgentNodeSpec(
            name="prepare_context",
            factory=create_prepare_context_node,
        ),
        AgentNodeSpec(
            name="prepare_semantics",
            factory=create_prepare_semantics_node,
        ),
        AgentNodeSpec(
            name="resolve_visual_semantics",
            factory=create_resolve_visual_semantics_node,
        ),
        AgentNodeSpec(
            name="validate_visual_result",
            factory=create_validate_visual_result_node,
        ),
    ],
    edges=[
        AgentEdgeSpec(source="prepare_context", target='prepare_semantics'),
        AgentEdgeSpec(source="prepare_semantics", target='resolve_visual_semantics'),
        AgentEdgeSpec(source="resolve_visual_semantics", target='validate_visual_result'),
        AgentEdgeSpec(source="validate_visual_result", target=END),
    ],
)

"""Declarative spec for the character_identity_resolver agent."""

from langgraph.graph import END

from app.runtime.langgraph.agent_definition import AgentDefinition, AgentEdgeSpec, AgentNodeSpec
from app.agents.prompt_generation.character_identity_resolver.nodes import prepare_context_node, collect_identities_node, resolve_identities_node, validate_identity_result_node
from app.agents.prompt_generation.character_identity_resolver.state import CharacterIdentityResolverState

CHARACTER_IDENTITY_RESOLVER_AGENT_NAME = "character_identity_resolver"
CHARACTER_IDENTITY_RESOLVER_ENTRYPOINT = "prepare_context"


def create_prepare_context_node():
    """Create the prepare_context node callable."""

    return prepare_context_node


def create_collect_identities_node():
    """Create the collect_identities node callable."""

    return collect_identities_node


def create_resolve_identities_node():
    """Create the resolve_identities node callable."""

    return resolve_identities_node


def create_validate_identity_result_node():
    """Create the validate_identity_result node callable."""

    return validate_identity_result_node


AGENT_DEFINITION = AgentDefinition(
    name=CHARACTER_IDENTITY_RESOLVER_AGENT_NAME,
    state_schema=CharacterIdentityResolverState,
    entrypoint=CHARACTER_IDENTITY_RESOLVER_ENTRYPOINT,
    nodes=[
        AgentNodeSpec(
            name="prepare_context",
            factory=create_prepare_context_node,
        ),
        AgentNodeSpec(
            name="collect_identities",
            factory=create_collect_identities_node,
        ),
        AgentNodeSpec(
            name="resolve_identities",
            factory=create_resolve_identities_node,
        ),
        AgentNodeSpec(
            name="validate_identity_result",
            factory=create_validate_identity_result_node,
        ),
    ],
    edges=[
        AgentEdgeSpec(source="prepare_context", target='collect_identities'),
        AgentEdgeSpec(source="collect_identities", target='resolve_identities'),
        AgentEdgeSpec(source="resolve_identities", target='validate_identity_result'),
        AgentEdgeSpec(source="validate_identity_result", target=END),
    ],
)

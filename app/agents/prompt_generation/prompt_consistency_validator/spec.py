"""Declarative spec for the prompt_consistency_validator agent."""

from langgraph.graph import END

from app.runtime.langgraph.agent_definition import AgentDefinition, AgentEdgeSpec, AgentNodeSpec
from app.agents.prompt_generation.prompt_consistency_validator.nodes import prepare_context_node, collect_invariants_node, validate_prompt_node, finalize_validation_node
from app.agents.prompt_generation.prompt_consistency_validator.state import PromptConsistencyValidatorState

PROMPT_CONSISTENCY_VALIDATOR_AGENT_NAME = "prompt_consistency_validator"
PROMPT_CONSISTENCY_VALIDATOR_ENTRYPOINT = "prepare_context"


def create_prepare_context_node():
    """Create the prepare_context node callable."""

    return prepare_context_node


def create_collect_invariants_node():
    """Create the collect_invariants node callable."""

    return collect_invariants_node


def create_validate_prompt_node():
    """Create the validate_prompt node callable."""

    return validate_prompt_node


def create_finalize_validation_node():
    """Create the finalize_validation node callable."""

    return finalize_validation_node


AGENT_DEFINITION = AgentDefinition(
    name=PROMPT_CONSISTENCY_VALIDATOR_AGENT_NAME,
    state_schema=PromptConsistencyValidatorState,
    entrypoint=PROMPT_CONSISTENCY_VALIDATOR_ENTRYPOINT,
    nodes=[
        AgentNodeSpec(
            name="prepare_context",
            factory=create_prepare_context_node,
        ),
        AgentNodeSpec(
            name="collect_invariants",
            factory=create_collect_invariants_node,
        ),
        AgentNodeSpec(
            name="validate_prompt",
            factory=create_validate_prompt_node,
        ),
        AgentNodeSpec(
            name="finalize_validation",
            factory=create_finalize_validation_node,
        ),
    ],
    edges=[
        AgentEdgeSpec(source="prepare_context", target='collect_invariants'),
        AgentEdgeSpec(source="collect_invariants", target='validate_prompt'),
        AgentEdgeSpec(source="validate_prompt", target='finalize_validation'),
        AgentEdgeSpec(source="finalize_validation", target=END),
    ],
)

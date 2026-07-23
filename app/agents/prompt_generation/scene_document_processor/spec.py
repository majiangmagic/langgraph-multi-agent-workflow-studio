"""Declarative spec for the scene_document_processor agent."""

from langgraph.graph import END

from app.agents.declarative import AgentDefinition, AgentEdgeSpec, AgentNodeSpec
from app.agents.prompt_generation.scene_document_processor.nodes import prepare_context_node, validate_patch_node, apply_patch_node, validate_document_node, build_agent_contexts_node
from app.agents.prompt_generation.scene_document_processor.state import SceneDocumentProcessorState

SCENE_DOCUMENT_PROCESSOR_AGENT_NAME = "scene_document_processor"
SCENE_DOCUMENT_PROCESSOR_ENTRYPOINT = "prepare_context"


def create_prepare_context_node():
    """Create the prepare_context node callable."""

    return prepare_context_node


def create_validate_patch_node():
    """Create the validate_patch node callable."""

    return validate_patch_node


def create_apply_patch_node():
    """Create the apply_patch node callable."""

    return apply_patch_node


def create_validate_document_node():
    """Create the validate_document node callable."""

    return validate_document_node


def create_build_agent_contexts_node():
    """Create the build_agent_contexts node callable."""

    return build_agent_contexts_node


AGENT_DEFINITION = AgentDefinition(
    name=SCENE_DOCUMENT_PROCESSOR_AGENT_NAME,
    state_schema=SceneDocumentProcessorState,
    entrypoint=SCENE_DOCUMENT_PROCESSOR_ENTRYPOINT,
    nodes=[
        AgentNodeSpec(
            name="prepare_context",
            factory=create_prepare_context_node,
        ),
        AgentNodeSpec(
            name="validate_patch",
            factory=create_validate_patch_node,
        ),
        AgentNodeSpec(
            name="apply_patch",
            factory=create_apply_patch_node,
        ),
        AgentNodeSpec(
            name="validate_document",
            factory=create_validate_document_node,
        ),
        AgentNodeSpec(
            name="build_agent_contexts",
            factory=create_build_agent_contexts_node,
        ),
    ],
    edges=[
        AgentEdgeSpec(source="prepare_context", target='validate_patch'),
        AgentEdgeSpec(source="validate_patch", target='apply_patch'),
        AgentEdgeSpec(source="apply_patch", target='validate_document'),
        AgentEdgeSpec(source="validate_document", target='build_agent_contexts'),
        AgentEdgeSpec(source="build_agent_contexts", target=END),
    ],
)

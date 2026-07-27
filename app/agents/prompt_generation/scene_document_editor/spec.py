"""Declarative spec for the scene_document_editor agent."""

from langgraph.graph import END

from app.runtime.langgraph.agent_definition import AgentDefinition, AgentEdgeSpec, AgentNodeSpec
from app.agents.prompt_generation.scene_document_editor.nodes import prepare_context_node, prepare_request_node, propose_patch_node, validate_patch_node
from app.agents.prompt_generation.scene_document_editor.state import SceneDocumentEditorState

SCENE_DOCUMENT_EDITOR_AGENT_NAME = "scene_document_editor"
SCENE_DOCUMENT_EDITOR_ENTRYPOINT = "prepare_context"


def create_prepare_context_node():
    """Create the prepare_context node callable."""

    return prepare_context_node


def create_prepare_request_node():
    """Create the prepare_request node callable."""

    return prepare_request_node


def create_propose_patch_node():
    """Create the propose_patch node callable."""

    return propose_patch_node


def create_validate_patch_node():
    """Create the validate_patch node callable."""

    return validate_patch_node


AGENT_DEFINITION = AgentDefinition(
    name=SCENE_DOCUMENT_EDITOR_AGENT_NAME,
    state_schema=SceneDocumentEditorState,
    entrypoint=SCENE_DOCUMENT_EDITOR_ENTRYPOINT,
    nodes=[
        AgentNodeSpec(
            name="prepare_context",
            factory=create_prepare_context_node,
        ),
        AgentNodeSpec(
            name="prepare_request",
            factory=create_prepare_request_node,
        ),
        AgentNodeSpec(
            name="propose_patch",
            factory=create_propose_patch_node,
        ),
        AgentNodeSpec(
            name="validate_patch",
            factory=create_validate_patch_node,
        ),
    ],
    edges=[
        AgentEdgeSpec(source="prepare_context", target='prepare_request'),
        AgentEdgeSpec(source="prepare_request", target='propose_patch'),
        AgentEdgeSpec(source="propose_patch", target='validate_patch'),
        AgentEdgeSpec(source="validate_patch", target=END),
    ],
)

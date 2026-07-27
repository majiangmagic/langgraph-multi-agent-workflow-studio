"""Declarative spec for the prompt_target_renderer agent."""

from langgraph.graph import END

from app.runtime.langgraph.agent_definition import AgentDefinition, AgentEdgeSpec, AgentNodeSpec
from app.agents.prompt_generation.prompt_target_renderer.nodes import prepare_context_node, validate_render_input_node, render_prompt_node, validate_render_result_node
from app.agents.prompt_generation.prompt_target_renderer.state import PromptTargetRendererState

PROMPT_TARGET_RENDERER_AGENT_NAME = "prompt_target_renderer"
PROMPT_TARGET_RENDERER_ENTRYPOINT = "prepare_context"


def create_prepare_context_node():
    """Create the prepare_context node callable."""

    return prepare_context_node


def create_validate_render_input_node():
    """Create the validate_render_input node callable."""

    return validate_render_input_node


def create_render_prompt_node():
    """Create the render_prompt node callable."""

    return render_prompt_node


def create_validate_render_result_node():
    """Create the validate_render_result node callable."""

    return validate_render_result_node


AGENT_DEFINITION = AgentDefinition(
    name=PROMPT_TARGET_RENDERER_AGENT_NAME,
    state_schema=PromptTargetRendererState,
    entrypoint=PROMPT_TARGET_RENDERER_ENTRYPOINT,
    nodes=[
        AgentNodeSpec(
            name="prepare_context",
            factory=create_prepare_context_node,
        ),
        AgentNodeSpec(
            name="validate_render_input",
            factory=create_validate_render_input_node,
        ),
        AgentNodeSpec(
            name="render_prompt",
            factory=create_render_prompt_node,
        ),
        AgentNodeSpec(
            name="validate_render_result",
            factory=create_validate_render_result_node,
        ),
    ],
    edges=[
        AgentEdgeSpec(source="prepare_context", target='validate_render_input'),
        AgentEdgeSpec(source="validate_render_input", target='render_prompt'),
        AgentEdgeSpec(source="render_prompt", target='validate_render_result'),
        AgentEdgeSpec(source="validate_render_result", target=END),
    ],
)

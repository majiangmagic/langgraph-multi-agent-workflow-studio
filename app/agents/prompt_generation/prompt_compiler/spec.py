"""Declarative spec for the prompt_compiler agent."""

from langgraph.graph import END

from app.runtime.langgraph.agent_definition import AgentDefinition, AgentEdgeSpec, AgentNodeSpec
from app.agents.prompt_generation.prompt_compiler.nodes import prepare_context_node, collect_terms_node, compile_prompt_node, validate_prompt_ir_node
from app.agents.prompt_generation.prompt_compiler.state import PromptCompilerState

PROMPT_COMPILER_AGENT_NAME = "prompt_compiler"
PROMPT_COMPILER_ENTRYPOINT = "prepare_context"


def create_prepare_context_node():
    """Create the prepare_context node callable."""

    return prepare_context_node


def create_collect_terms_node():
    """Create the collect_terms node callable."""

    return collect_terms_node


def create_compile_prompt_node():
    """Create the compile_prompt node callable."""

    return compile_prompt_node


def create_validate_prompt_ir_node():
    """Create the validate_prompt_ir node callable."""

    return validate_prompt_ir_node


AGENT_DEFINITION = AgentDefinition(
    name=PROMPT_COMPILER_AGENT_NAME,
    state_schema=PromptCompilerState,
    entrypoint=PROMPT_COMPILER_ENTRYPOINT,
    nodes=[
        AgentNodeSpec(
            name="prepare_context",
            factory=create_prepare_context_node,
        ),
        AgentNodeSpec(
            name="collect_terms",
            factory=create_collect_terms_node,
        ),
        AgentNodeSpec(
            name="compile_prompt",
            factory=create_compile_prompt_node,
        ),
        AgentNodeSpec(
            name="validate_prompt_ir",
            factory=create_validate_prompt_ir_node,
        ),
    ],
    edges=[
        AgentEdgeSpec(source="prepare_context", target='collect_terms'),
        AgentEdgeSpec(source="collect_terms", target='compile_prompt'),
        AgentEdgeSpec(source="compile_prompt", target='validate_prompt_ir'),
        AgentEdgeSpec(source="validate_prompt_ir", target=END),
    ],
)

"""Declarative spec for the prompt_format_converter agent."""

from langgraph.graph import END

from app.agents.declarative import AgentDefinition, AgentEdgeSpec, AgentNodeSpec
from app.agents.prompt_generation.format_converter.nodes import convert_node
from app.agents.prompt_generation.format_converter.state import PromptFormatConverterState

PROMPT_FORMAT_CONVERTER_AGENT_NAME = "prompt_format_converter"
PROMPT_FORMAT_CONVERTER_ENTRYPOINT = "convert"


def create_convert_node():
    """Create the convert node callable."""

    return convert_node


AGENT_DEFINITION = AgentDefinition(
    name=PROMPT_FORMAT_CONVERTER_AGENT_NAME,
    state_schema=PromptFormatConverterState,
    entrypoint=PROMPT_FORMAT_CONVERTER_ENTRYPOINT,
    nodes=[
        AgentNodeSpec(
            name="convert",
            factory=create_convert_node,
        ),
    ],
    edges=[
        AgentEdgeSpec(source="convert", target=END),
    ],
)

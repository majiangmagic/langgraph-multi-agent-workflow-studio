"""Declarative spec for the prompt_writer agent."""

from langgraph.graph import END

from app.agents.declarative import AgentDefinition, AgentEdgeSpec, AgentNodeSpec
from app.agents.prompt_generation.prompt_writer.nodes import write_prompt_node
from app.agents.prompt_generation.prompt_writer.state import PromptWriterState

PROMPT_WRITER_AGENT_NAME = "prompt_writer"
PROMPT_WRITER_ENTRYPOINT = "write_prompt"


def create_write_prompt_node():
    """Create the write_prompt node callable."""

    return write_prompt_node


AGENT_DEFINITION = AgentDefinition(
    name=PROMPT_WRITER_AGENT_NAME,
    state_schema=PromptWriterState,
    entrypoint=PROMPT_WRITER_ENTRYPOINT,
    nodes=[
        AgentNodeSpec(
            name="write_prompt",
            factory=create_write_prompt_node,
        ),
    ],
    edges=[
        AgentEdgeSpec(source="write_prompt", target=END),
    ],
)

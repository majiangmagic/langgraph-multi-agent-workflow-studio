"""Declarative spec for the prompt_requirement_analyzer agent."""

from langgraph.graph import END

from app.agents.declarative import AgentDefinition, AgentEdgeSpec, AgentNodeSpec
from app.agents.prompt_generation.requirement_analyzer.nodes import analyze_node
from app.agents.prompt_generation.requirement_analyzer.state import PromptRequirementAnalyzerState

PROMPT_REQUIREMENT_ANALYZER_AGENT_NAME = "prompt_requirement_analyzer"
PROMPT_REQUIREMENT_ANALYZER_ENTRYPOINT = "analyze"


def create_analyze_node():
    """Create the analyze node callable."""

    return analyze_node


AGENT_DEFINITION = AgentDefinition(
    name=PROMPT_REQUIREMENT_ANALYZER_AGENT_NAME,
    state_schema=PromptRequirementAnalyzerState,
    entrypoint=PROMPT_REQUIREMENT_ANALYZER_ENTRYPOINT,
    nodes=[
        AgentNodeSpec(
            name="analyze",
            factory=create_analyze_node,
        ),
    ],
    edges=[
        AgentEdgeSpec(source="analyze", target=END),
    ],
)

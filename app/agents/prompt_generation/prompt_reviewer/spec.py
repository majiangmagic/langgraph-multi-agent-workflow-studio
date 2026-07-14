"""Declarative spec for the prompt_reviewer agent."""

from langgraph.graph import END

from app.agents.declarative import AgentDefinition, AgentEdgeSpec, AgentNodeSpec
from app.agents.prompt_generation.prompt_reviewer.nodes import review_node
from app.agents.prompt_generation.prompt_reviewer.state import PromptReviewerState

PROMPT_REVIEWER_AGENT_NAME = "prompt_reviewer"
PROMPT_REVIEWER_ENTRYPOINT = "review"


def create_review_node():
    """Create the review node callable."""

    return review_node


AGENT_DEFINITION = AgentDefinition(
    name=PROMPT_REVIEWER_AGENT_NAME,
    state_schema=PromptReviewerState,
    entrypoint=PROMPT_REVIEWER_ENTRYPOINT,
    nodes=[
        AgentNodeSpec(
            name="review",
            factory=create_review_node,
        ),
    ],
    edges=[
        AgentEdgeSpec(source="review", target=END),
    ],
)

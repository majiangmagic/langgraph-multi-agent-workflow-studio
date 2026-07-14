"""Declarative spec for the prompt_danbooru_query agent."""

from langgraph.graph import END

from app.agents.declarative import AgentDefinition, AgentEdgeSpec, AgentNodeSpec
from app.agents.prompt_generation.danbooru_query.nodes import query_tags_node
from app.agents.prompt_generation.danbooru_query.state import PromptDanbooruQueryState

PROMPT_DANBOORU_QUERY_AGENT_NAME = "prompt_danbooru_query"
PROMPT_DANBOORU_QUERY_ENTRYPOINT = "query_tags"


def create_query_tags_node():
    """Create the query_tags node callable."""

    return query_tags_node


AGENT_DEFINITION = AgentDefinition(
    name=PROMPT_DANBOORU_QUERY_AGENT_NAME,
    state_schema=PromptDanbooruQueryState,
    entrypoint=PROMPT_DANBOORU_QUERY_ENTRYPOINT,
    nodes=[
        AgentNodeSpec(
            name="query_tags",
            factory=create_query_tags_node,
        ),
    ],
    edges=[
        AgentEdgeSpec(source="query_tags", target=END),
    ],
)

"""Tests for the prompt generation workflow example."""

from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage

from app.core.langgraph.workflows.prompt_generation_workflow.graph import (
    create_prompt_generation_workflow_graph,
)
from app.core.langgraph.workflows.prompt_generation_workflow.state import (
    build_initial_state,
)


def prompt_generation_agents():
    """Return DB-shaped agent configs required by the prompt workflow."""

    return [
        {
            "id": "agent-supervisor",
            "name": "official_supervisor",
            "description": "Coordinates prompt generation.",
            "system_prompt": "Coordinate prompt generation agents.",
            "model": "test-model",
            "temperature": 0.2,
            "tools": [],
        },
        {
            "id": "agent-requirements",
            "name": "prompt_requirement_analyzer",
            "description": "Extracts structured requirements.",
            "system_prompt": "Analyze requirements.",
            "model": "test-model",
            "temperature": 0.2,
            "tools": [],
        },
        {
            "id": "agent-danbooru",
            "name": "prompt_danbooru_query",
            "description": "Maps requirements to Danbooru tags.",
            "system_prompt": "Map tags.",
            "model": "test-model",
            "temperature": 0.2,
            "tools": [],
        },
        {
            "id": "agent-writer",
            "name": "prompt_writer",
            "description": "Writes prompt drafts.",
            "system_prompt": "Write prompts.",
            "model": "test-model",
            "temperature": 0.4,
            "tools": [],
        },
        {
            "id": "agent-reviewer",
            "name": "prompt_reviewer",
            "description": "Reviews prompt drafts.",
            "system_prompt": "Review prompts.",
            "model": "test-model",
            "temperature": 0.2,
            "tools": [],
        },
        {
            "id": "agent-converter",
            "name": "prompt_format_converter",
            "description": "Converts prompt formats.",
            "system_prompt": "Convert prompt formats.",
            "model": "test-model",
            "temperature": 0.2,
            "tools": [],
        },
    ]


@pytest.mark.asyncio
async def test_prompt_generation_workflow_runs_grouped_agents():
    """The prompt workflow should pass upstream outputs through grouped agents."""

    def fake_supervisor_invoke(state, config=None):
        return {
            "messages": [
                AIMessage(
                    content="Prompt generation pipeline approved.",
                    name="official_supervisor",
                )
            ],
            "plan": {"steps": ["analyze", "tag", "write", "review", "convert"]},
        }

    user_input = "Create a flux cyberpunk portrait of a girl in a rainy night city"
    initial_state = build_initial_state(
        crew_id="crew-1",
        agents=prompt_generation_agents(),
        user_id="user-1",
        conversation_id="conversation-1",
        user_input=user_input,
    )
    workflow = create_prompt_generation_workflow_graph(
        crew_id="crew-1",
        agents=prompt_generation_agents(),
    )

    with patch(
        "app.agents.official_supervisor.official_runtime."
        "OfficialSupervisorRuntime.invoke",
        side_effect=fake_supervisor_invoke,
    ):
        result = await workflow.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": "prompt-generation-test"}},
        )

    nodes = result["nodes"]
    assert nodes["requirement_analyzer"]["requirements_json"]["target_model"] == "flux"
    assert "cyberpunk" in nodes["danbooru_query"]["danbooru_tags"]
    assert "neon_lights" in nodes["prompt_writer"]["draft_prompt"]
    assert nodes["prompt_reviewer"]["review_result"]["approved"] is True
    assert nodes["format_converter"]["final_output"]["target_model"] == "flux"
    assert "Create an image of" in nodes["format_converter"]["formatted_prompt"]

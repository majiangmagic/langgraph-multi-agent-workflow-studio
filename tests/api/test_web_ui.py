"""Tests for the lightweight web UI entrypoints."""

from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import select

from app.db.base import get_db
from app.main import app
from app.models.crew import Agent


client = TestClient(app)


def test_web_app_serves_index():
    response = client.get("/")

    assert response.status_code == 200
    assert "Prompt Workflow Studio" in response.text
    assert "/static/app.js" in response.text
    assert "创建示例 Crew" in response.text
    assert 'id="deleteLastTurnButton"' in response.text
    assert 'id="deleteConversationButton"' in response.text
    assert 'id="progressList" class="pipeline-track"></div>' in response.text


def test_workflow_options_endpoint_lists_registered_workflows():
    response = client.get("/api/workflows/")

    assert response.status_code == 200
    workflows = response.json()
    names = {workflow["name"] for workflow in workflows}
    assert "supervisor_simple" in names
    assert "prompt_generation_workflow" in names
    assert any(workflow["is_default"] for workflow in workflows)
    prompt_workflow = next(
        workflow
        for workflow in workflows
        if workflow["name"] == "prompt_generation_workflow"
    )
    assert prompt_workflow["entrypoint"] == "supervisor"
    assert {node["name"] for node in prompt_workflow["nodes"]} == {
        "supervisor",
        "natural_language_editor",
        "requirement_analyzer",
        "character_prompt_generator",
        "scene_prompt_generator",
        "additional_prompt_generator",
        "prompt_aggregator",
        "format_optimizer",
    }
    assert prompt_workflow["ui"]["default_target_model"] == "nai_v4"


@pytest.mark.asyncio
async def test_create_sample_crew_for_prompt_workflow(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/api/workflows/prompt_generation_workflow/sample-crew"
            )
            second_response = await client.post(
                "/api/workflows/prompt_generation_workflow/sample-crew"
            )

        assert response.status_code == 200
        assert second_response.status_code == 200
        crew = response.json()
        second_crew = second_response.json()
        assert crew["settings"]["workflow_type"] == "prompt_generation_workflow"
        assert crew["name"] == "prompt_generation_workflow demo 1"
        assert second_crew["name"] == "prompt_generation_workflow demo 2"

        agents = (await db_session.execute(select(Agent))).scalars().all()
        names = {agent.name for agent in agents}
        assert names == {
            "official_supervisor",
            "natural_language_editor",
            "prompt_requirement_analyzer",
            "character_prompt_generator",
            "scene_prompt_generator",
            "additional_prompt_generator",
            "prompt_aggregator",
            "prompt_format_optimizer",
        }
        assert len(agents) == 16
    finally:
        app.dependency_overrides.pop(get_db, None)

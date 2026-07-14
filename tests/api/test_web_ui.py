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
    assert "Agent Workflow Kit" in response.text
    assert "/static/app.js" in response.text
    assert "创建示例 Crew" in response.text


def test_workflow_options_endpoint_lists_registered_workflows():
    response = client.get("/api/workflows/")

    assert response.status_code == 200
    workflows = response.json()
    names = {workflow["name"] for workflow in workflows}
    assert "supervisor_simple" in names
    assert "prompt_generation_workflow" in names
    assert any(workflow["is_default"] for workflow in workflows)


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

        assert response.status_code == 200
        crew = response.json()
        assert crew["settings"]["workflow_type"] == "prompt_generation_workflow"

        agents = (await db_session.execute(select(Agent))).scalars().all()
        names = {agent.name for agent in agents}
        assert "official_supervisor" in names
        assert "prompt_requirement_analyzer" in names
        assert "prompt_format_converter" in names
        assert len(agents) == 6
    finally:
        app.dependency_overrides.pop(get_db, None)

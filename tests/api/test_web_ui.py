"""Tests for the lightweight web UI entrypoints."""

from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
import pytest

from app.db.base import Base, get_db
from app.main import app


client = TestClient(app)


def test_web_app_serves_index():
    response = client.get("/")

    assert response.status_code == 200
    assert "Agent Workflow Studio" in response.text
    assert 'id="root"' in response.text
    assert "/static/assets/index-" in response.text


def test_web_app_serves_built_react_assets():
    response = client.get("/")
    asset_path = response.text.split('src="')[1].split('"')[0]
    asset_response = client.get(asset_path)

    assert asset_response.status_code == 200
    assert "javascript" in asset_response.headers["content-type"]


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
        "scene_document_editor",
            "scene_document_processor",
            "identity_impact_router",
            "character_identity_resolver",
            "visual_impact_router",
        "visual_semantic_resolver",
        "prompt_compiler",
        "consistency_validator",
        "semantic_repairer",
        "target_renderer",
    }
    conditional_edges = [
        edge for edge in prompt_workflow["edges"] if edge.get("conditional")
    ]
    assert {edge["to"] for edge in conditional_edges} == {
        "scene_document_editor",
        "scene_document_processor",
        "identity_impact_router",
        "character_identity_resolver",
        "visual_impact_router",
        "visual_semantic_resolver",
        "prompt_compiler",
        "consistency_validator",
        "semantic_repairer",
        "target_renderer",
        "END",
    }
    assert all(edge["from"] == "supervisor" for edge in conditional_edges)
    supervisor = next(
        node for node in prompt_workflow["nodes"] if node["name"] == "supervisor"
    )
    assert "虚构成年 NSFW" in supervisor["config"]["prompt"]
    assert {
        edge["to"]
        for edge in prompt_workflow["edges"]
        if edge["from"] == "supervisor"
    } >= {"scene_document_editor", "target_renderer", "END"}
    controls = {
        control["key"]: control for control in prompt_workflow["ui"]["controls"]
    }
    assert controls["prompt_strategy"]["default"] == "expressive"
    assert controls["target_model"]["default"] == "nai_v4"


def test_database_agent_api_and_tables_are_removed():
    assert client.get("/api/agents/").status_code == 404
    assert "agents" not in Base.metadata.tables
    assert "agent_tools" not in Base.metadata.tables


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
            detail_response = await client.get(
                f"/api/crews/{response.json()['id']}"
            )

        assert response.status_code == 200
        assert second_response.status_code == 200
        assert detail_response.status_code == 200
        assert detail_response.json()["mcp_servers"] == []
        crew = response.json()
        second_crew = second_response.json()
        assert crew["workflow_type"] == "prompt_generation_workflow"
        assert crew["settings"] == {}
        assert crew["workflow_missing"] is False
        assert crew["name"] == "prompt_generation_workflow demo 1"
        assert second_crew["name"] == "prompt_generation_workflow demo 2"

    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_crew_with_missing_workflow_remains_visible(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            created = await client.post(
                "/api/crews/",
                json={
                    "name": "Missing workflow crew",
                    "workflow_type": "removed_workflow",
                },
            )
            crews = await client.get("/api/crews/")

        assert created.status_code == 201
        assert created.json()["workflow_type"] == "removed_workflow"
        assert created.json()["workflow_missing"] is True
        listed = next(item for item in crews.json() if item["id"] == created.json()["id"])
        assert listed["workflow_missing"] is True
    finally:
        app.dependency_overrides.pop(get_db, None)

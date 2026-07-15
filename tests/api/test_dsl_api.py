"""API coverage for local DSL design and generation."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services import dsl_service


client = TestClient(app)


def agent_document(name: str = "test_designer_agent") -> dict:
    return {
        "version": 1,
        "kind": "agent",
        "name": name,
        "display_name": "测试 Agent",
        "entrypoint": "start",
        "nodes": {"start": {"handler": "start_node"}},
        "edges": [{"from": "start", "to": "END"}],
    }


def test_validate_and_save_agent_dsl(tmp_path: Path, monkeypatch):
    monkeypatch.setitem(dsl_service.DSL_DIRS, "agent", tmp_path)
    document = agent_document()

    validate_response = client.post("/api/dsl/agent/validate", json={"data": document})
    assert validate_response.status_code == 200
    assert validate_response.json()["nodes"] == ["start"]

    save_response = client.put(
        "/api/dsl/agent/test_designer_agent",
        json={"data": document},
    )
    assert save_response.status_code == 200
    assert (tmp_path / "test_designer_agent.json").exists()

    list_response = client.get("/api/dsl/agent")
    assert list_response.status_code == 200
    assert list_response.json()[0]["display_name"] == "测试 Agent"


def test_dsl_name_cannot_escape_examples_directory(tmp_path: Path, monkeypatch):
    monkeypatch.setitem(dsl_service.DSL_DIRS, "agent", tmp_path)
    response = client.put(
        "/api/dsl/agent/..%2Foutside",
        json={"data": agent_document("outside")},
    )
    assert response.status_code in {404, 422}
    assert not (tmp_path.parent / "outside.json").exists()

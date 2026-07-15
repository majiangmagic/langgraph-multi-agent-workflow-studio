"""End-to-end API tests for the chat workflow path."""

import uuid
import json

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage
from sqlalchemy import select
from unittest.mock import patch

from app.db.base import get_db
from app.main import app
from app.models.conversation import Message, MessageRole
from app.models.crew import Agent
from app.services.ai_provider import AIProvider


@pytest.mark.asyncio
async def test_create_crew_agents_and_chat_end_to_end(db_session):
    """Create crew/agents, chat once, and verify messages are persisted."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            crew_response = await client.post(
                "/api/crews/",
                json={
                    "name": "E2E Crew",
                    "description": "End-to-end test crew",
                    "settings": {"workflow_type": "supervisor_simple"},
                },
            )
            assert crew_response.status_code == 201
            crew_id = crew_response.json()["id"]

            supervisor_response = await client.post(
                "/api/agents/",
                json={
                    "crew_id": crew_id,
                    "name": "Supervisor",
                    "system_prompt": "You coordinate the crew.",
                    "is_supervisor": True,
                },
            )
            assert supervisor_response.status_code == 201
            assert supervisor_response.json()["model"] == AIProvider.SUPERVISOR_MODEL

            worker_response = await client.post(
                "/api/agents/",
                json={
                    "crew_id": crew_id,
                    "name": "Writer",
                    "system_prompt": "You write concise responses.",
                    "is_supervisor": False,
                },
            )
            assert worker_response.status_code == 201
            assert worker_response.json()["model"] == AIProvider.DEFAULT_MODEL

            def fake_official_supervisor_invoke(state, config=None):
                return {
                    **state,
                    "messages": state["messages"]
                    + [AIMessage(content="E2E workflow response")],
                    "action": None,
                }

            with patch(
                "app.agents.official_supervisor.official_runtime."
                "OfficialSupervisorRuntime.invoke",
                side_effect=fake_official_supervisor_invoke,
            ):
                chat_response = await client.post(
                    "/api/chat",
                    json={
                        "user_id": "e2e-user",
                        "crew_id": crew_id,
                        "title": "E2E Chat",
                        "message": "Hello through the full API path",
                    },
                )

            assert chat_response.status_code == 200
            chat_data = chat_response.json()
            assert chat_data["conversation_id"]
            assert chat_data["message_id"]
            assert chat_data["content"] == "E2E workflow response"

            messages_response = await client.get(
                f"/api/conversations/{chat_data['conversation_id']}/messages"
            )
            assert messages_response.status_code == 200
            messages = messages_response.json()
            assert [message["role"] for message in messages] == ["user", "assistant"]
            assert messages[0]["content"] == "Hello through the full API path"
            assert messages[1]["content"] == "E2E workflow response"

        db_messages = (
            await db_session.execute(
                select(Message).where(
                    Message.conversation_id
                    == uuid.UUID(chat_data["conversation_id"])
                )
            )
        ).scalars().all()
        assert len(db_messages) == 2
        assert {message.role for message in db_messages} == {
            MessageRole.USER,
            MessageRole.ASSISTANT,
        }

        db_agents = (await db_session.execute(select(Agent))).scalars().all()
        assert len(db_agents) == 2
        assert any(agent.is_supervisor for agent in db_agents)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_chat_stream_includes_workflow_node_events(db_session):
    """Streaming chat should expose visible workflow progress events."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            crew_response = await client.post(
                "/api/crews/",
                json={
                    "name": "Stream Crew",
                    "description": "Streaming test crew",
                    "settings": {"workflow_type": "supervisor_simple"},
                },
            )
            crew_id = crew_response.json()["id"]
            supervisor_response = await client.post(
                "/api/agents/",
                json={
                    "crew_id": crew_id,
                    "name": "supervisor",
                    "system_prompt": "You coordinate the crew.",
                    "is_supervisor": True,
                },
            )
            assert supervisor_response.status_code == 201
            conversation_response = await client.post(
                "/api/conversations/",
                json={
                    "user_id": "stream-user",
                    "crew_id": crew_id,
                    "title": "Stream Chat",
                },
            )
            conversation_id = conversation_response.json()["id"]

            captured_workflow_inputs = {}

            def fake_official_supervisor_invoke(state, config=None):
                captured_workflow_inputs.update(state.get("workflow_inputs") or {})
                return {
                    **state,
                    "messages": state["messages"]
                    + [AIMessage(content="Stream workflow response")],
                    "action": None,
                }

            with patch(
                "app.agents.official_supervisor.official_runtime."
                "OfficialSupervisorRuntime.invoke",
                side_effect=fake_official_supervisor_invoke,
            ):
                response = await client.post(
                    f"/api/conversations/{conversation_id}/chat/stream",
                    json={
                        "message": "Hello through stream",
                        "workflow_inputs": {
                            "prompt_strategy": "faithful",
                            "target_model": "nai_v4",
                        },
                    },
                )

            assert response.status_code == 200
            assert captured_workflow_inputs == {
                "prompt_strategy": "faithful",
                "target_model": "nai_v4",
            }
            events = []
            for block in response.text.strip().split("\n\n"):
                if not block.startswith("data: "):
                    continue
                raw = block.removeprefix("data: ")
                if raw == "[DONE]":
                    events.append("[DONE]")
                else:
                    events.append(json.loads(raw))

            event_types = [
                event["type"]
                for event in events
                if isinstance(event, dict) and event.get("object") == "workflow.event"
            ]
            assert "workflow.started" in event_types
            assert "workflow.node.started" in event_types
            assert "workflow.node.completed" in event_types
            assert "workflow.completed" in event_types
            assert any(
                isinstance(event, dict)
                and event.get("object") == "chat.completion.chunk"
                and event["choices"][0]["delta"].get("content")
                == "Stream workflow response"
                for event in events
            )
            assert events[-1] == "[DONE]"
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_delete_latest_turn_removes_last_user_and_assistant_messages(db_session):
    """Deleting the latest turn should preserve earlier conversation history."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            crew_response = await client.post(
                "/api/crews/",
                json={
                    "name": "Delete Turn Crew",
                    "description": "Test latest turn deletion",
                    "settings": {"workflow_type": "supervisor_simple"},
                },
            )
            crew_id = crew_response.json()["id"]

            conversation_response = await client.post(
                "/api/conversations/",
                json={
                    "user_id": "delete-turn-user",
                    "crew_id": crew_id,
                    "title": "Delete turn chat",
                },
            )
            conversation_id = conversation_response.json()["id"]

            for role, content in [
                ("user", "first question"),
                ("assistant", "first answer"),
                ("user", "bad question"),
                ("assistant", "bad answer"),
            ]:
                response = await client.post(
                    f"/api/conversations/{conversation_id}/messages",
                    json={"role": role, "content": content},
                )
                assert response.status_code == 201

            delete_response = await client.delete(
                f"/api/conversations/{conversation_id}/turns/latest"
            )
            assert delete_response.status_code == 200
            assert delete_response.json()["deleted_messages"] == 2

            messages_response = await client.get(
                f"/api/conversations/{conversation_id}/messages"
            )
            messages = messages_response.json()

        assert [message["content"] for message in messages] == [
            "first question",
            "first answer",
        ]
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_rewind_from_selected_turn_removes_that_turn_and_everything_after(db_session):
    """A selected historical user turn should become the rewind boundary."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            crew = await client.post(
                "/api/crews/",
                json={"name": "Rewind Crew", "settings": {"workflow_type": "supervisor_simple"}},
            )
            conversation = await client.post(
                "/api/conversations/",
                json={"user_id": "rewind-user", "crew_id": crew.json()["id"]},
            )
            conversation_id = conversation.json()["id"]

            message_ids = []
            for role, content in [
                ("user", "keep question"),
                ("assistant", "keep answer"),
                ("user", "rewrite this"),
                ("assistant", "old answer"),
                ("user", "later question"),
                ("assistant", "later answer"),
            ]:
                response = await client.post(
                    f"/api/conversations/{conversation_id}/messages",
                    json={"role": role, "content": content},
                )
                message_ids.append(response.json()["id"])

            rewind = await client.delete(
                f"/api/conversations/{conversation_id}/turns/from/{message_ids[2]}"
            )
            assert rewind.status_code == 200
            assert rewind.json()["deleted_messages"] == 4

            messages = await client.get(
                f"/api/conversations/{conversation_id}/messages"
            )
            assert [item["content"] for item in messages.json()] == [
                "keep question",
                "keep answer",
            ]
    finally:
        app.dependency_overrides.pop(get_db, None)

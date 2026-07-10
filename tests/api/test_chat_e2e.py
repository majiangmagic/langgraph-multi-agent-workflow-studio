"""End-to-end API tests for the chat workflow path."""

import uuid

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

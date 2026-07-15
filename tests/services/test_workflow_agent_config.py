"""Tests for preserving agent runtime configuration in workflows."""

import pytest
from types import SimpleNamespace
from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph
from langgraph.store.memory import InMemoryStore

from app.agents.official_supervisor.official_runtime import OfficialSupervisorRuntime
from app.core.langgraph.workflows.adapters.agent import (
    create_agent_node,
    create_pipeline_context_extension,
    trim_agent_memory,
)
from app.core.langgraph.workflows.adapters.supervisor import create_supervisor_extension
from app.core.langgraph.workflows.declarative import (
    RESET_NODE_STATE_KEY,
    merge_node_states,
)
from app.core.langgraph.workflows.supervisor_simple.state import (
    SupervisorSimpleState,
    build_initial_state,
)
from app.services.workflow_service import WorkflowService


def test_workflow_runtime_uses_local_agent_manifest():
    crew = SimpleNamespace(
        id="crew-1",
        workflow_type="supervisor_simple",
    )

    local_agents = WorkflowService.local_agent_configs(crew)
    workflow = WorkflowService.create_workflow(crew)

    assert workflow is not None
    assert len(local_agents) == 1
    assert local_agents[0]["name"] == "official_supervisor"
    assert local_agents[0]["system_prompt"]
    assert local_agents[0]["model"]


def test_missing_workflow_cannot_run():
    crew = SimpleNamespace(
        id="crew-1",
        workflow_type="removed_workflow",
    )

    with pytest.raises(ValueError, match="references missing workflow"):
        WorkflowService.create_workflow(crew)


def test_delegated_agent_prompt_is_preserved_in_workflow_state():
    """Worker agent prompts should survive the handoff into workflow state."""

    state = build_initial_state(
        crew_id="crew-1",
        agents=[
            {
                "id": "supervisor-1",
                "name": "official_supervisor",
                "system_prompt": "You coordinate this crew.",
            },
            {
                "id": "writer-1",
                "name": "Writer",
                "description": "Creates concise user-facing summaries.",
                "system_prompt": "You write concise responses.",
                "model": "worker-model",
                "temperature": 0.4,
                "tools": [{"name": "draft"}],
            }
        ],
        conversation_id="conversation-1",
        user_input="Summarize this.",
    )

    supervisor_state = state["nodes"]["supervisor"]
    writer_state = state["agents"]["writer"]

    assert set(state["nodes"]) == {"supervisor"}
    assert set(state["agents"]) == {"official_supervisor", "writer"}
    assert supervisor_state["agent_id"] == "supervisor-1"
    assert supervisor_state["system_prompt"] == "You coordinate this crew."
    assert writer_state["agent_name"] == "Writer"
    assert writer_state["description"] == "Creates concise user-facing summaries."
    assert writer_state["system_prompt"] == "You write concise responses."
    assert writer_state["model"] == "worker-model"
    assert writer_state["temperature"] == 0.4
    assert writer_state["tools"] == [{"name": "draft"}]


def test_official_supervisor_prompt_includes_worker_instructions():
    """The official supervisor should see enough worker config to delegate well."""

    runtime = OfficialSupervisorRuntime(
        system_prompt="You coordinate this crew.",
        model_name="supervisor-model",
    )
    state = build_initial_state(
        crew_id="crew-1",
        agents=[
            {
                "id": "supervisor-1",
                "name": "official_supervisor",
                "system_prompt": "You coordinate this crew.",
            },
            {
                "id": "writer-1",
                "name": "Writer",
                "description": "Creates concise user-facing summaries.",
                "system_prompt": "You write concise responses.",
                "model": "worker-model",
                "temperature": 0.4,
                "tools": [],
            }
        ],
    )

    prompt = runtime._build_prompt(
        {"writer": "writer"},
        {
            **state["nodes"]["supervisor"],
            "agents": {
                "writer": state["agents"]["writer"],
            },
        },
    )

    assert "You coordinate this crew." in prompt
    assert "description=Creates concise user-facing summaries." in prompt
    assert "instructions=You write concise responses." in prompt
    assert "model=worker-model" in prompt


def test_official_supervisor_prompt_includes_long_term_memories():
    """Supervisor prompt should expose memories attached from the store."""

    runtime = OfficialSupervisorRuntime(system_prompt="You coordinate this crew.")

    prompt = runtime._build_prompt(
        {},
        {
            **build_initial_state(crew_id="crew-1", agents=[
                {
                    "id": "supervisor-1",
                    "name": "official_supervisor",
                    "system_prompt": "You coordinate this crew.",
                }
            ])["nodes"]["supervisor"],
            "agents": {},
            "long_term_memories": [
                {
                    "content": "The user prefers concise engineering explanations.",
                }
            ],
        },
    )

    assert "Long-term memories:" in prompt
    assert "The user prefers concise engineering explanations." in prompt


def test_checkpointed_supervisor_messages_survive_new_turn_input():
    """A fresh turn should update user_input without clearing checkpoint memory."""

    current = {
        "supervisor": {
            "messages": [AIMessage(content="Earlier answer")],
            "user_input": None,
            "plan": None,
            "action": None,
            "agents": {},
        }
    }
    update = {
        "supervisor": {
            "messages": [],
            "user_input": "Continue the conversation",
            "plan": None,
            "action": None,
            "agents": {},
        }
    }

    merged = merge_node_states(current, update)

    assert merged["supervisor"]["messages"] == current["supervisor"]["messages"]
    assert merged["supervisor"]["user_input"] == "Continue the conversation"


def test_new_turn_discards_checkpointed_business_outputs():
    """A new turn must not expose stale downstream outputs to pipeline nodes."""

    current = {
        "scene_prompt_generator": {
            "messages": [AIMessage(content="Earlier answer")],
            "user_input": "Earlier request",
            "scene_tags": ["indoors"],
            "formatted_prompt": "stale prompt",
        }
    }
    update = {
        "scene_prompt_generator": {
            RESET_NODE_STATE_KEY: True,
            "messages": [],
            "user_input": "Background is a street",
            "status": "idle",
        }
    }

    merged = merge_node_states(current, update)

    assert merged["scene_prompt_generator"]["messages"] == current[
        "scene_prompt_generator"
    ]["messages"]
    assert merged["scene_prompt_generator"]["user_input"] == (
        "Background is a street"
    )
    assert "scene_tags" not in merged["scene_prompt_generator"]
    assert "formatted_prompt" not in merged["scene_prompt_generator"]
    assert RESET_NODE_STATE_KEY not in merged["scene_prompt_generator"]


def test_pipeline_context_does_not_reuse_stale_downstream_output():
    current = {
        "requirement_analyzer": {
            "requirements_json": {"scene": "room"},
        },
        "scene_prompt_generator": {
            "scene_tags": ["indoors"],
        },
        "format_optimizer": {
            "requirements_json": {"scene": "room"},
            "formatted_prompt": "old result",
        },
    }
    fresh = {
        node_name: {
            RESET_NODE_STATE_KEY: True,
            "messages": [],
            "user_input": "Background is a street",
        }
        for node_name in current
    }
    merged = merge_node_states(current, fresh)
    merged = merge_node_states(
        merged,
        {
            "requirement_analyzer": {
                **merged["requirement_analyzer"],
                "requirements_json": {"scene": "street"},
            }
        },
    )

    extension = create_pipeline_context_extension("scene_prompt_generator")
    scene_state = extension.prepare_agent_state(
        {
            "nodes": merged,
            "user_input": "Background is a street",
        }
    )

    assert scene_state["requirements_json"] == {"scene": "street"}
    assert "formatted_prompt" not in scene_state


def test_short_term_memory_keeps_last_ten_turns():
    """Short-term memory should keep the recent 20 messages by default."""

    messages = [AIMessage(content=f"message-{index}") for index in range(25)]

    trimmed = trim_agent_memory(
        {
            "messages": messages,
            "agents": {
                "writer": {
                    "messages": messages,
                }
            },
        }
    )

    assert len(trimmed["messages"]) == 20
    assert trimmed["messages"][0].content == "message-5"
    assert len(trimmed["agents"]["writer"]["messages"]) == 20
    assert trimmed["agents"]["writer"]["messages"][0].content == "message-5"


@pytest.mark.asyncio
async def test_plain_agent_node_does_not_use_long_term_memory_store():
    """Plain agents should not read or write long-term memory automatically."""

    captured = {}

    class EchoAgent:
        async def ainvoke(self, state, config=None):
            captured["memories"] = state.get("long_term_memories")
            return {
                **state,
                "messages": [AIMessage(content="Remembered response")],
            }

    store = InMemoryStore()
    await store.aput(
        ("memories", "user-1"),
        "memory-1",
        {"content": "The user likes direct answers."},
        index=False,
    )

    workflow = StateGraph(SupervisorSimpleState)
    workflow.add_node("supervisor", create_agent_node("supervisor", EchoAgent()))
    workflow.add_edge("supervisor", END)
    workflow.set_entry_point("supervisor")
    graph = workflow.compile(store=store)

    await graph.ainvoke(
        {
            "nodes": {
                "supervisor": {
                    "agent_id": "supervisor-1",
                    "agent_name": "supervisor",
                    "messages": [],
                    "user_input": "Hello",
                }
            },
            "agents": {},
            "user_id": "user-1",
            "crew_id": "crew-1",
            "conversation_id": "conversation-1",
            "user_input": "Hello",
        }
    )

    stored = await store.asearch(("memories", "user-1"), limit=10)

    assert captured["memories"] is None
    assert len(stored) == 1
    assert stored[0].value == {"content": "The user likes direct answers."}


@pytest.mark.asyncio
async def test_supervisor_extension_reads_and_explicitly_writes_long_term_memory():
    """Supervisor extension owns long-term memory context and writes."""

    captured = {}

    class SupervisorAgent:
        async def ainvoke(self, state, config=None):
            captured["memories"] = state.get("long_term_memories")
            return {
                **state,
                "messages": [AIMessage(content="Supervisor response")],
                "memory_write": {
                    "kind": "user_preference",
                    "content": "The user likes direct answers.",
                },
            }

    store = InMemoryStore()
    await store.aput(
        ("memories", "user-1"),
        "memory-1",
        {"content": "The user prefers concise explanations."},
        index=False,
    )

    workflow = StateGraph(SupervisorSimpleState)
    workflow.add_node(
        "supervisor",
        create_agent_node(
            "supervisor",
            SupervisorAgent(),
            extension=create_supervisor_extension("supervisor"),
        ),
    )
    workflow.add_edge("supervisor", END)
    workflow.set_entry_point("supervisor")
    graph = workflow.compile(store=store)

    await graph.ainvoke(
        {
            "nodes": {
                "supervisor": {
                    "agent_id": "supervisor-1",
                    "agent_name": "supervisor",
                    "messages": [],
                    "user_input": "Hello",
                }
            },
            "agents": {},
            "user_id": "user-1",
            "crew_id": "crew-1",
            "conversation_id": "conversation-1",
            "user_input": "Hello",
        }
    )

    stored = await store.asearch(("memories", "user-1"), limit=10)

    assert captured["memories"] == [
        {"content": "The user prefers concise explanations."}
    ]
    assert any(
        item.value.get("kind") == "user_preference"
        and item.value.get("content") == "The user likes direct answers."
        for item in stored
    )

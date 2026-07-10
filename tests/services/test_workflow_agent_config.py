"""Tests for preserving agent runtime configuration in workflows."""

from app.agents.supervisor.official_runtime import OfficialSupervisorRuntime
from app.core.langgraph.workflows.supervisor_simple.state import build_initial_state


def test_delegated_agent_prompt_is_preserved_in_workflow_state():
    """Worker agent prompts should survive the handoff into workflow state."""

    state = build_initial_state(
        crew_id="crew-1",
        agents=[
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

    writer_state = state["supervisor"]["agents"]["writer-1"]

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

    prompt = runtime._build_prompt({"writer": "writer-1"}, state["supervisor"])

    assert "You coordinate this crew." in prompt
    assert "description=Creates concise user-facing summaries." in prompt
    assert "instructions=You write concise responses." in prompt
    assert "model=worker-model" in prompt

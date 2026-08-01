"""Tests for an official Supervisor connected with native conditional edges."""

from typing import Any, Dict, List, Optional, TypedDict

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.graph import END, START, StateGraph
from pydantic import PrivateAttr

from app.agents.official_supervisor.workflow_supervisor import (
    create_workflow_supervisor_graph,
)
from app.runtime.langgraph.adapters.agent import (
    create_agent_node,
    create_pipeline_context_extension,
)
from app.runtime.langgraph.adapters.supervisor import (
    create_supervisor_extension,
)
from app.runtime.langgraph.declarative import (
    WorkflowState,
    build_workflow_initial_state,
)


class WorkerState(TypedDict, total=False):
    messages: List[BaseMessage]
    user_input: Optional[str]
    result_value: str


def worker_graph():
    graph = StateGraph(WorkerState)

    def execute(state: WorkerState) -> Dict[str, Any]:
        return {
            "result_value": f"processed:{state.get('user_input')}",
            "messages": [AIMessage(content="worker complete", name="worker")],
        }

    graph.add_node("execute", execute)
    graph.add_edge("execute", END)
    graph.set_entry_point("execute")
    return graph.compile()


class SupervisorTestModel(BaseChatModel):
    _tool_names: List[str] = PrivateAttr(default_factory=list)
    _system_contents: List[str] = PrivateAttr(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "supervisor-test"

    def bind_tools(self, tools, **kwargs):
        self._tool_names = [tool.name for tool in tools]
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self._system_contents.append(str(messages[0].content))
        worker_completed = '"worker": {' in str(messages[0].content)
        if worker_completed:
            response = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "finish_workflow",
                        "args": {},
                        "id": "finish-1",
                    }
                ],
            )
        else:
            response = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "route_to_worker",
                        "args": {},
                        "id": "delegate-1",
                    }
                ],
            )
        return ChatResult(generations=[ChatGeneration(message=response)])


def runtime_agents():
    return [
        {
            "id": "local:official_supervisor:supervisor",
            "name": "official_supervisor",
            "description": "Controls the test workflow",
            "system_prompt": "Run worker and finish.",
            "model": "test",
            "temperature": 0.0,
            "tools": [],
        },
        {
            "id": "local:worker:worker",
            "name": "worker",
            "description": "Processes one value",
            "system_prompt": "",
            "model": "test",
            "temperature": 0.0,
            "tools": [],
        },
    ]


def initial_state():
    return build_workflow_initial_state(
        workflow_name="test",
        node_agents={"supervisor": "official_supervisor", "worker": "worker"},
        user_id="user",
        crew_id="crew",
        agents=runtime_agents(),
        conversation_id="conversation",
        messages=[],
        user_input="input",
    )


def supervised_workflow(model, *, checkpointer=None):
    worker = create_agent_node(
        "worker",
        worker_graph(),
        extension=create_pipeline_context_extension("worker"),
    )
    supervisor = create_workflow_supervisor_graph(
        node_name="supervisor",
        agents=runtime_agents(),
        worker_names=["worker"],
        max_retries_per_node=2,
    )
    workflow = StateGraph(WorkflowState)
    workflow.add_node(
        "supervisor",
        create_agent_node(
            "supervisor",
            supervisor,
            extension=create_supervisor_extension("supervisor"),
        ),
    )
    workflow.add_node("worker", worker)
    workflow.add_edge(START, "supervisor")
    workflow.add_edge("worker", "supervisor")
    workflow.add_conditional_edges(
        "supervisor",
        lambda state: state["nodes"]["supervisor"]["next_node"],
        {"worker": "worker", "END": END},
    )
    return workflow.compile(checkpointer=checkpointer).with_config(
        {"recursion_limit": 12}
    )


def test_supervisor_can_disable_finish_tool(monkeypatch):
    model = SupervisorTestModel()
    monkeypatch.setattr(
        "app.agents.official_supervisor.workflow_supervisor.ai_provider.get_model",
        lambda **kwargs: model,
    )

    create_workflow_supervisor_graph(
        node_name="supervisor",
        agents=runtime_agents(),
        worker_names=["worker"],
        allow_finish_workflow=False,
    )

    assert "route_to_worker" in model._tool_names
    assert "finish_workflow" not in model._tool_names
    assert "request_user_input" not in model._tool_names


@pytest.mark.asyncio
async def test_official_supervisor_runs_real_worker_and_merges_state(monkeypatch):
    model = SupervisorTestModel()
    monkeypatch.setattr(
        "app.agents.official_supervisor.workflow_supervisor.ai_provider.get_model",
        lambda **kwargs: model,
    )
    workflow = supervised_workflow(model)

    result = await workflow.ainvoke(initial_state())

    assert result["nodes"]["worker"]["result_value"] == "processed:input"
    assert any(
        tool_call.get("name") == "route_to_worker"
        for message in result["nodes"]["supervisor"]["messages"]
        if isinstance(message, AIMessage)
        for tool_call in message.tool_calls
    )
    assert "route_to_worker" in model._tool_names
    assert any('"completed": true' in content for content in model._system_contents)
    assert all("processed:input" not in content for content in model._system_contents)



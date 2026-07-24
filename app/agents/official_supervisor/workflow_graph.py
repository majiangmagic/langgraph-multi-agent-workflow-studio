"""Supervisor Agent used by workflows with explicit conditional edges."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, tool
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from app.agents.official_supervisor.state import SupervisorState
from app.core.langgraph.events import emit_event
from app.services.ai_provider import ai_provider


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, BaseMessage):
        return {"type": value.type, "content": str(value.content)}
    return str(value)


@tool
def request_user_input(
    question: str,
    options: Optional[list[str]] = None,
    context: str = "",
) -> str:
    """Pause the workflow and request information required to continue."""

    return "The workflow will pause and pass the user's answer back to you."


def create_route_tool(target: str) -> BaseTool:
    """Create a tool schema for selecting an outer conditional edge."""

    tool_name = "finish_workflow" if target == "END" else f"route_to_{target}"
    description = (
        "Finish the workflow and return its current final result"
        if target == "END"
        else f"Select workflow node '{target}' as the next step"
    )

    @tool(tool_name, description=description)
    def route() -> str:
        return f"Selected next workflow node: {target}"

    return route


def _find_agent_config(
    agents: list[Dict[str, Any]],
    node_name: str,
) -> Dict[str, Any]:
    for config in agents:
        identifier = str(config.get("id") or "")
        if identifier.endswith(f":{node_name}") or config.get("name") == node_name:
            return config
    raise ValueError(f"Supervisor node '{node_name}' has no local Agent config")


def _control_state(state: SupervisorState, worker_names: list[str]) -> Dict[str, Any]:
    worker_runs = {name: 0 for name in worker_names}
    worker_reports: Dict[str, Dict[str, Any]] = {}
    last_worker = None
    for message in state.get("messages") or []:
        if not isinstance(message, AIMessage):
            continue
        for tool_call in message.tool_calls:
            tool_name = str(tool_call.get("name") or "")
            if not tool_name.startswith("route_to_"):
                continue
            worker_name = tool_name.removeprefix("route_to_")
            if worker_name in worker_runs:
                worker_runs[worker_name] += 1
                last_worker = worker_name

    agents = state.get("agents") or {}
    for worker_name, agent in agents.items():
        results = agent.get("results") or {}
        has_result = any(value not in (None, "", [], {}) for value in results.values())
        if worker_name in worker_runs and has_result:
            worker_runs[worker_name] = max(worker_runs[worker_name], 1)
        status = agent.get("status")
        error = agent.get("error")
        if worker_name in worker_runs and (
            has_result or error or status not in (None, "", "idle")
        ):
            worker_reports[worker_name] = {
                "status": status,
                "error": error,
                "results": _json_safe(results),
            }

    last_agent = agents.get(last_worker or "") or {}
    return {
        "worker_runs": {name: count for name, count in worker_runs.items() if count},
        # Directly connected workers do not create Supervisor route messages.
        # Expose every completed report so the Supervisor can inspect stage outputs.
        "worker_reports": worker_reports,
        "last_worker": last_worker,
        "last_report": {
            "status": last_agent.get("status"),
            "error": last_agent.get("error"),
            "results": _json_safe(last_agent.get("results")),
        }
        if last_worker
        else None,
    }


def _latest_tool_call(state: SupervisorState) -> Dict[str, Any]:
    for message in reversed(state.get("messages") or []):
        if isinstance(message, AIMessage) and message.tool_calls:
            return message.tool_calls[0]
    raise ValueError("Supervisor must select exactly one routing or clarification tool")


def create_workflow_supervisor_graph(
    *,
    node_name: str,
    agents: list[Dict[str, Any]],
    worker_names: list[str],
    max_retries_per_node: int = 2,
):
    """Create a Supervisor Agent that writes its choice to ``next_node``."""

    supervisor_config = _find_agent_config(agents, node_name)
    system_prompt = str(supervisor_config.get("system_prompt") or "").strip()
    worker_configs = {
        str(config.get("id") or "").rsplit(":", 1)[-1]: config for config in agents
    }
    worker_descriptions = "\n".join(
        f"- {worker_name}: "
        f"{worker_configs.get(worker_name, {}).get('description') or worker_name}"
        for worker_name in worker_names
    )
    route_targets = {
        **{f"route_to_{worker_name}": worker_name for worker_name in worker_names},
        "finish_workflow": "END",
    }
    tools = [request_user_input, *[create_route_tool(name) for name in [*worker_names, "END"]]]
    model = ai_provider.get_model(
        model_name=supervisor_config.get("model") or ai_provider.SUPERVISOR_MODEL,
        temperature=supervisor_config.get("temperature", 0.2),
    ).bind_tools(tools)

    def supervisor_messages(state: SupervisorState) -> list[BaseMessage]:
        control_context = _control_state(state, worker_names)
        memory_lines = [
            f"- {memory.get('content')}"
            for memory in state.get("long_term_memories") or []
            if isinstance(memory, dict) and memory.get("content")
        ]
        memory_section = (
            "\nLong-term memories:\n" + "\n".join(memory_lines)
            if memory_lines
            else ""
        )
        policy = f"""

You supervise an explicit LangGraph workflow. Select the next node by calling
exactly one route_to_* tool. Call finish_workflow only when the final output is
ready. Available workers:
{worker_descriptions}

- Inspect the latest worker result before selecting the next node.
- Inspect worker_reports for outputs produced by directly connected stage nodes.
- Do not run a worker more than {max_retries_per_node + 1} times per turn.
- If required user information is missing, call request_user_input.
- Do not fabricate business output or bypass the declared workflow order.

Current control state:
{json.dumps(control_context, ensure_ascii=False)}
"""
        return [
            SystemMessage(content=f"{system_prompt}{policy}{memory_section}"),
            *state.get("messages", []),
        ]

    async def decide(state: SupervisorState) -> Dict[str, Any]:
        response = await model.ainvoke(supervisor_messages(state))
        if not isinstance(response, AIMessage) or len(response.tool_calls) != 1:
            raise ValueError("Supervisor must call exactly one routing or clarification tool")
        return {"messages": [response], "next_node": ""}

    def after_decide(state: SupervisorState) -> str:
        tool_name = str(_latest_tool_call(state).get("name") or "")
        return "clarify" if tool_name == "request_user_input" else "select_route"

    def clarify(state: SupervisorState) -> Dict[str, Any]:
        tool_call = _latest_tool_call(state)
        arguments = tool_call.get("args") or {}
        payload = {
            "kind": "workflow.clarification",
            "question": str(arguments.get("question") or "").strip(),
            "options": [
                str(option)
                for option in (arguments.get("options") or [])
                if str(option).strip()
            ][:4],
            "context": str(arguments.get("context") or "").strip(),
        }
        emit_event(
            {
                "object": "workflow.event",
                "type": "workflow.interrupted",
                "interrupt": payload,
            }
        )
        answer = interrupt(payload)
        return {
            "messages": [
                ToolMessage(
                    content=json.dumps(
                        {"status": "user_replied", "answer": _json_safe(answer)},
                        ensure_ascii=False,
                    ),
                    name="request_user_input",
                    tool_call_id=str(tool_call.get("id") or "request-user-input"),
                )
            ]
        }

    def select_route(state: SupervisorState) -> Dict[str, Any]:
        tool_call = _latest_tool_call(state)
        tool_name = str(tool_call.get("name") or "")
        if tool_name not in route_targets:
            raise ValueError(f"Unknown Supervisor routing tool: {tool_name}")
        target = route_targets[tool_name]
        return {
            "next_node": target,
            "messages": [
                ToolMessage(
                    content=f"Selected next workflow node: {target}",
                    name=tool_name,
                    tool_call_id=str(tool_call.get("id") or tool_name),
                )
            ],
        }

    graph = StateGraph(SupervisorState)
    graph.add_node("decide", decide)
    graph.add_node("clarify", clarify)
    graph.add_node("select_route", select_route)
    graph.set_entry_point("decide")
    graph.add_conditional_edges(
        "decide",
        after_decide,
        {"clarify": "clarify", "select_route": "select_route"},
    )
    graph.add_edge("clarify", "decide")
    graph.add_edge("select_route", END)
    return graph.compile()

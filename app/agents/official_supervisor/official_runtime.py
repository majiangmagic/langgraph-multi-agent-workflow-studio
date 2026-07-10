"""Adapter around the official langgraph-supervisor engine."""

import re
from typing import Any, Dict, List, Tuple

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, MessagesState, StateGraph
from langgraph_supervisor import create_supervisor

from app.agents.official_supervisor.state import DelegatedAgentState, SupervisorState
from app.core.langgraph.events import emit_event
from app.services.ai_provider import ai_provider


DEFAULT_SUPERVISOR_PROMPT = (
    "You are the supervisor of a multi-agent workflow. Coordinate available "
    "agents when useful, answer directly when delegation is unnecessary, and "
    "be explicit when no real delegated agent executor is connected."
)


def normalize_agent_runtime_name(name: str, used_names: set[str]) -> str:
    """Create a stable graph/tool-safe name for the official supervisor."""

    base = re.sub(r"[^a-zA-Z0-9_]+", "_", name.strip()).strip("_").lower()
    if not base:
        base = "agent"

    candidate = base
    suffix = 2
    while candidate in used_names:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used_names.add(candidate)
    return candidate


def message_text(message: BaseMessage) -> str:
    """Return message content as text for simple status inspection."""

    content = message.content
    if isinstance(content, str):
        return content
    return str(content)


def build_unavailable_agent_graph(
    runtime_name: str,
    agent: DelegatedAgentState,
):
    """Create a truthful placeholder graph until a real AgentExecutor exists."""

    def unavailable_agent_node(state: MessagesState) -> Dict[str, List[BaseMessage]]:
        task = ""
        for message in reversed(state.get("messages", [])):
            if isinstance(message, HumanMessage):
                task = message_text(message)
                break

        error = (
            f"{agent['agent_name']} received delegated work"
            f"{f': {task}' if task else ''}, but no real agent executor is "
            "connected for this agent yet."
        )
        emit_event(
            {
                "object": "workflow.event",
                "type": "workflow.task.assigned",
                "scope": "supervisor",
                "agent_id": agent["agent_id"],
                "agent_name": agent["agent_name"],
                "task": task,
            }
        )
        emit_event(
            {
                "object": "workflow.event",
                "type": "workflow.agent.error",
                "scope": "supervisor",
                "agent_id": agent["agent_id"],
                "agent_name": agent["agent_name"],
                "task": task,
                "error": error,
            }
        )
        return {"messages": [AIMessage(content=error, name=runtime_name)]}

    graph = StateGraph(MessagesState)
    graph.add_node("unavailable_agent", unavailable_agent_node)
    graph.add_edge("unavailable_agent", END)
    graph.set_entry_point("unavailable_agent")
    return graph.compile(name=runtime_name)


def build_official_messages(state: SupervisorState) -> List[BaseMessage]:
    """Build the official supervisor message input from our state shape."""

    messages = list(state.get("messages") or [])
    user_input = state.get("user_input")
    if user_input:
        messages.append(HumanMessage(content=user_input))
    return messages


class OfficialSupervisorRuntime:
    """Runs the official supervisor while preserving this project's state API."""

    def __init__(
        self,
        *,
        system_prompt: str | None = None,
        model_name: str | None = None,
        temperature: float = 0.2,
    ) -> None:
        self.system_prompt = system_prompt or DEFAULT_SUPERVISOR_PROMPT
        self.model_name = model_name or ai_provider.SUPERVISOR_MODEL
        self.temperature = temperature

    def with_state_config(self, state: SupervisorState) -> "OfficialSupervisorRuntime":
        """Return a runtime configured from the agent state when available."""

        return OfficialSupervisorRuntime(
            system_prompt=state.get("system_prompt") or self.system_prompt,
            model_name=state.get("model") or self.model_name,
            temperature=state.get("temperature", self.temperature),
        )

    def invoke(
        self,
        state: SupervisorState,
        config: RunnableConfig | None = None,
    ) -> SupervisorState:
        """Run the official supervisor graph and map its result back."""

        emit_event(
            {
                "object": "workflow.event",
                "type": "workflow.node.started",
                "scope": "supervisor",
                "node": "official_supervisor",
            }
        )

        official_agents, runtime_to_agent_key = self._build_agent_graphs(state)
        model = ai_provider.get_model(
            model_name=self.model_name,
            temperature=self.temperature,
        )
        workflow = create_supervisor(
            official_agents,
            model=model,
            prompt=self._build_prompt(runtime_to_agent_key, state),
            output_mode="full_history",
            handoff_tool_prefix="delegate_to",
            include_agent_name="inline",
        ).compile()

        result = workflow.invoke(
            {"messages": build_official_messages(state)},
            config=config,
        )
        updated_state = self._map_result(state, result.get("messages", []))

        emit_event(
            {
                "object": "workflow.event",
                "type": "workflow.node.completed",
                "scope": "supervisor",
                "node": "official_supervisor",
                "summary": self._summarize(updated_state),
            }
        )
        return updated_state

    def _build_agent_graphs(
        self, state: SupervisorState
    ) -> Tuple[List[Any], Dict[str, str]]:
        used_names: set[str] = set()
        graphs = []
        runtime_to_agent_key = {}

        for agent_key, agent in (state.get("agents") or {}).items():
            runtime_name = normalize_agent_runtime_name(agent["agent_name"], used_names)
            runtime_to_agent_key[runtime_name] = agent_key
            graphs.append(build_unavailable_agent_graph(runtime_name, agent))

        return graphs, runtime_to_agent_key

    def _build_prompt(
        self,
        runtime_to_agent_key: Dict[str, str],
        state: SupervisorState,
    ) -> str:
        agent_lines = []
        for runtime_name, agent_key in runtime_to_agent_key.items():
            agent = state["agents"][agent_key]
            details = [
                f"name={agent['agent_name']}",
                f"agent_id={agent['agent_id']}",
            ]
            if agent.get("description"):
                details.append(f"description={agent['description']}")
            if agent.get("system_prompt"):
                details.append(f"instructions={agent['system_prompt']}")
            if agent.get("model"):
                details.append(f"model={agent['model']}")

            agent_lines.append(f"- {runtime_name}: " + "; ".join(details))

        if not agent_lines:
            return (
                f"{self.system_prompt}\n\n"
                "No delegated agents are currently available. Answer directly."
            )

        return (
            f"{self.system_prompt}\n\n"
            "Available delegated agents:\n"
            + "\n".join(agent_lines)
            + "\n\nOnly delegate when one of these agents is clearly useful."
        )

    def _map_result(
        self,
        state: SupervisorState,
        messages: List[BaseMessage],
    ) -> SupervisorState:
        updated_agents = {key: {**agent} for key, agent in state["agents"].items()}
        used_names: set[str] = set()
        agent_key_to_runtime = {
            agent_key: normalize_agent_runtime_name(agent["agent_name"], used_names)
            for agent_key, agent in updated_agents.items()
        }

        for agent_key, agent in updated_agents.items():
            runtime_name = agent_key_to_runtime[agent_key]
            agent_messages = [
                message
                for message in messages
                if getattr(message, "name", None) == runtime_name
            ]
            if not agent_messages:
                continue

            last_message = agent_messages[-1]
            content = message_text(last_message)
            agent["messages"] = list(agent.get("messages") or []) + agent_messages
            if "no real agent executor is connected" in content:
                agent["status"] = "error"
                agent["results"] = {"error": content}
                agent["error"] = content
            else:
                agent["status"] = "complete"
                agent["results"] = {"content": content}
                agent["error"] = None

        return {
            **state,
            "messages": messages,
            "agents": updated_agents,
            "plan": None,
            "action": None,
            "user_input": None,
        }

    def _summarize(self, state: SupervisorState) -> Dict[str, Any]:
        return {
            "action": str(state.get("action") or ""),
            "plan_steps": len((state.get("plan") or {}).get("steps", [])),
            "agents": [
                {
                    "agent_id": agent.get("agent_id") or agent_key,
                    "agent_name": agent.get("agent_name"),
                    "status": agent.get("status"),
                    "error": agent.get("error"),
                }
                for agent_key, agent in (state.get("agents") or {}).items()
            ],
        }

"""Generic adapter for running an agent graph as a workflow node."""

import inspect
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.langgraph.events import emit_event

AgentStatePreparer = Callable[[Dict[str, Any]], Dict[str, Any]]
WorkflowUpdateBuilder = Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]
AgentNodeExtensionFactory = Callable[[str], "AgentNodeExtension"]

RUNTIME_STATE_FIELDS = {
    "agent_id",
    "agent_name",
    "description",
    "system_prompt",
    "model",
    "temperature",
    "tools",
    "messages",
    "user_input",
    "workflow_inputs",
    "plan",
    "action",
    "agents",
    "status",
    "results",
    "error",
}


@dataclass(frozen=True)
class AgentNodeExtension:
    """Optional extension for agents that need custom workflow integration."""

    prepare_agent_state: AgentStatePreparer
    build_workflow_update: WorkflowUpdateBuilder


def create_pipeline_context_extension(
    node_name: str,
    inputs: Optional[Dict[str, str]] = None,
) -> AgentNodeExtension:
    """Expose upstream business fields to a generated workflow node."""

    def prepare_agent_state(state: Dict[str, Any]) -> Dict[str, Any]:
        context: Dict[str, Any] = {"user_input": state.get("user_input")}
        if inputs:
            for target_field, source_path in inputs.items():
                source_node, separator, source_field = source_path.partition(".")
                if source_node == "$workflow":
                    value = state.get(source_field)
                elif separator:
                    value = (state.get("nodes") or {}).get(source_node, {}).get(
                        source_field
                    )
                else:
                    value = None
                if value is not None:
                    context[target_field] = value
            return {**state["nodes"][node_name], **context}
        for current_name, node_state in (state.get("nodes") or {}).items():
            if current_name == node_name:
                continue
            for key, value in node_state.items():
                if key in RUNTIME_STATE_FIELDS or value is None:
                    continue
                if isinstance(value, list) and isinstance(context.get(key), list):
                    merged_values = list(context[key])
                    for item in value:
                        if item not in merged_values:
                            merged_values.append(item)
                    context[key] = merged_values
                else:
                    context[key] = value
        return {**state["nodes"][node_name], **context}

    def build_workflow_update(
        state: Dict[str, Any],
        updated_agent_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {"nodes": {node_name: updated_agent_state}}

    return AgentNodeExtension(
        prepare_agent_state=prepare_agent_state,
        build_workflow_update=build_workflow_update,
    )


def trim_agent_memory(agent_state: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only the recent short-term message window in an agent state."""

    max_messages = max(settings.short_term_memory_turns, 0) * 2
    if max_messages == 0:
        return agent_state

    trimmed = dict(agent_state)
    messages = trimmed.get("messages")
    if isinstance(messages, list) and len(messages) > max_messages:
        trimmed["messages"] = messages[-max_messages:]

    agents = trimmed.get("agents")
    if isinstance(agents, dict):
        trimmed["agents"] = {
            agent_name: trim_agent_memory(agent)
            if isinstance(agent, dict)
            else agent
            for agent_name, agent in agents.items()
        }

    return trimmed


async def maybe_await(value):
    """Await values returned by async extension hooks."""

    if inspect.isawaitable(value):
        return await value
    return value


def create_agent_node(
    agent_name: str,
    agent_graph: Any,
    extension: Optional[AgentNodeExtension] = None,
    continue_on_error: bool = False,
):
    """Create a workflow node from a reusable agent graph."""

    async def run_agent(
        state: Dict[str, Any],
        config: RunnableConfig | None = None,
    ) -> Dict[str, Any]:
        """Run one agent graph and return only the workflow fields it updates."""

        emit_event(
            {
                "object": "workflow.event",
                "type": "workflow.node.started",
                "node": agent_name,
            }
        )
        try:
            agent_state = (
                await maybe_await(extension.prepare_agent_state(state))
                if extension is not None
                else state["nodes"][agent_name]
            )
            agent_state = trim_agent_memory(agent_state)
            updated_agent_state = await agent_graph.ainvoke(agent_state, config=config)
            updated_agent_state = trim_agent_memory(updated_agent_state)

            emit_event(
                {
                    "object": "workflow.event",
                    "type": "workflow.node.completed",
                    "node": agent_name,
                }
            )
            if extension is not None:
                return await maybe_await(
                    extension.build_workflow_update(state, updated_agent_state)
                )
            return {"nodes": {agent_name: updated_agent_state}}
        except Exception as exc:
            emit_event(
                {
                    "object": "workflow.event",
                    "type": "workflow.node.error",
                    "node": agent_name,
                    "error": str(exc),
                }
            )
            if continue_on_error:
                failed_state = {
                    **state["nodes"][agent_name],
                    "status": "error",
                    "error": str(exc),
                    "messages": [
                        *state["nodes"][agent_name].get("messages", []),
                        AIMessage(
                            content=f"{agent_name} failed and the workflow continued.",
                            name=agent_name,
                        ),
                    ],
                }
                return {"nodes": {agent_name: failed_state}}
            raise

    return run_agent

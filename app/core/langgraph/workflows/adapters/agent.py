"""Generic adapter for running an agent graph as a workflow node."""

import inspect
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from langchain_core.runnables import RunnableConfig

from app.core.config import settings

AgentStatePreparer = Callable[[Dict[str, Any]], Dict[str, Any]]
WorkflowUpdateBuilder = Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]
AgentNodeExtensionFactory = Callable[[str], "AgentNodeExtension"]


@dataclass(frozen=True)
class AgentNodeExtension:
    """Optional extension for agents that need custom workflow integration."""

    prepare_agent_state: AgentStatePreparer
    build_workflow_update: WorkflowUpdateBuilder


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
):
    """Create a workflow node from a reusable agent graph."""

    async def run_agent(
        state: Dict[str, Any],
        config: RunnableConfig | None = None,
    ) -> Dict[str, Any]:
        """Run one agent graph and return only the workflow fields it updates."""

        agent_state = (
            await maybe_await(extension.prepare_agent_state(state))
            if extension is not None
            else state["nodes"][agent_name]
        )
        agent_state = trim_agent_memory(agent_state)
        updated_agent_state = await agent_graph.ainvoke(agent_state, config=config)
        updated_agent_state = trim_agent_memory(updated_agent_state)

        if extension is not None:
            return await maybe_await(
                extension.build_workflow_update(state, updated_agent_state)
            )
        return {"nodes": {agent_name: updated_agent_state}}

    return run_agent

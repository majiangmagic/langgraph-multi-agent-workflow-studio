"""Graph factory for the orchestrated workflow."""

import uuid
from typing import Dict, List

from langgraph.graph import END, StateGraph

from app.core.langgraph.workflows.orchestrated.nodes import (
    analyze_input,
    answer_directly,
    assign_tasks,
    check_status,
    combine_results,
    create_plan,
)
from app.core.langgraph.workflows.orchestrated.router import route_by_action
from app.core.langgraph.workflows.orchestrated.state import (
    OrchestratedAction,
    OrchestratedState,
)
from app.core.langgraph.workflows.registry import workflow_registry


def build_initial_state(crew_id: str, agents: List[Dict]) -> OrchestratedState:
    """Build the initial state for an orchestrated crew."""

    agent_states = {}
    for agent_config in agents:
        agent_id = agent_config.get("id") or str(uuid.uuid4())
        agent_states[agent_id] = {
            "agent_id": agent_id,
            "agent_name": agent_config["name"],
            "messages": [],
            "status": "idle",
            "results": None,
            "tools": agent_config.get("tools", []),
        }

    return {
        "messages": [],
        "user_input": None,
        "plan": None,
        "agents": agent_states,
        "crew_id": crew_id,
        "conversation_id": "",
        "action": None,
    }


def create_orchestrated_graph(crew_id: str, agents: List[Dict], system_prompt: str = None):
    """Create a compiled LangGraph for an orchestrated agent crew."""

    workflow = StateGraph(OrchestratedState)

    workflow.add_node("analyze_input", analyze_input)
    workflow.add_node("answer_directly", answer_directly)
    workflow.add_node("create_plan", create_plan)
    workflow.add_node("assign_tasks", assign_tasks)
    workflow.add_node("check_status", check_status)
    workflow.add_node("combine_results", combine_results)

    workflow.add_conditional_edges(
        "analyze_input",
        route_by_action,
        {
            OrchestratedAction.ANSWER_DIRECTLY: "answer_directly",
            OrchestratedAction.CREATE_PLAN: "create_plan",
        },
    )
    workflow.add_edge("create_plan", "assign_tasks")
    workflow.add_edge("assign_tasks", "check_status")
    workflow.add_conditional_edges(
        "check_status",
        route_by_action,
        {
            OrchestratedAction.ASSIGN_TASKS: "assign_tasks",
            OrchestratedAction.CHECK_STATUS: "check_status",
            OrchestratedAction.COMBINE_RESULTS: "combine_results",
        },
    )
    workflow.add_edge("answer_directly", END)
    workflow.add_edge("combine_results", END)
    workflow.set_entry_point("analyze_input")

    return workflow.compile()


workflow_registry.register("orchestrated", create_orchestrated_graph)
workflow_registry.register("supervisor", create_orchestrated_graph)

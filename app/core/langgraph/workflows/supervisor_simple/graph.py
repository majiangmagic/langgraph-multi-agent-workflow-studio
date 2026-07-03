"""Graph connections for the simple supervisor workflow."""

from typing import Dict, List

from langgraph.graph import END, StateGraph

from app.agents.supervisor.nodes import (
    analyze_input,
    answer_directly,
    assign_tasks,
    check_status,
    combine_results,
    create_plan,
)
from app.agents.supervisor.router import route_by_action
from app.agents.supervisor.state import SupervisorAction
from app.core.langgraph.workflows.supervisor_simple.state import (
    SupervisorState,
)
from app.core.langgraph.workflows.registry import workflow_registry


def create_supervisor_simple_graph(
    crew_id: str, agents: List[Dict], system_prompt: str = None
):
    """Create a compiled LangGraph for a simple supervisor agent crew."""

    workflow = StateGraph(SupervisorState)

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
            SupervisorAction.ANSWER_DIRECTLY: "answer_directly",
            SupervisorAction.CREATE_PLAN: "create_plan",
        },
    )
    workflow.add_edge("create_plan", "assign_tasks")
    workflow.add_edge("assign_tasks", "check_status")
    workflow.add_conditional_edges(
        "check_status",
        route_by_action,
        {
            SupervisorAction.ASSIGN_TASKS: "assign_tasks",
            SupervisorAction.CHECK_STATUS: "check_status",
            SupervisorAction.COMBINE_RESULTS: "combine_results",
        },
    )
    workflow.add_edge("answer_directly", END)
    workflow.add_edge("combine_results", END)
    workflow.set_entry_point("analyze_input")

    return workflow.compile()


workflow_registry.register("supervisor_simple", create_supervisor_simple_graph)

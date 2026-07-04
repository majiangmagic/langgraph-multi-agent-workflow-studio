"""Internal graph for the supervisor agent."""

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
    SupervisorSimpleState,
)


def create_supervisor_graph():
    """Create the supervisor agent's internal LangGraph."""

    graph = StateGraph(SupervisorSimpleState)

    graph.add_node("analyze_input", analyze_input)
    graph.add_node("answer_directly", answer_directly)
    graph.add_node("create_plan", create_plan)
    graph.add_node("assign_tasks", assign_tasks)
    graph.add_node("check_status", check_status)
    graph.add_node("combine_results", combine_results)

    graph.add_conditional_edges(
        "analyze_input",
        route_by_action,
        {
            SupervisorAction.ANSWER_DIRECTLY: "answer_directly",
            SupervisorAction.CREATE_PLAN: "create_plan",
        },
    )
    graph.add_edge("create_plan", "assign_tasks")
    graph.add_edge("assign_tasks", "check_status")
    graph.add_conditional_edges(
        "check_status",
        route_by_action,
        {
            SupervisorAction.ASSIGN_TASKS: "assign_tasks",
            SupervisorAction.CHECK_STATUS: "check_status",
            SupervisorAction.COMBINE_RESULTS: "combine_results",
        },
    )
    graph.add_edge("answer_directly", END)
    graph.add_edge("combine_results", END)
    graph.set_entry_point("analyze_input")

    return graph.compile()

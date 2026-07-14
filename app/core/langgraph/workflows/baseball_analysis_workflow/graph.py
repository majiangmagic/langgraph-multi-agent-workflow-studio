"""Graph factory for the baseball_analysis_workflow workflow."""

from typing import Any, Dict, List

from app.agents.baseball_analysis_agent.graph import (
    create_graph as create_baseball_analysis_agent_graph,
)
from app.agents.official_supervisor.graph import create_official_supervisor_graph
from langgraph.graph import END, StateGraph

from app.core.langgraph.checkpoint import get_checkpointer
from app.core.langgraph.store import get_store
from app.core.langgraph.workflows.adapters.agent import create_agent_node
from app.core.langgraph.workflows.adapters.supervisor import create_supervisor_extension
from app.core.langgraph.workflows.registry import workflow_registry
from app.core.langgraph.workflows.baseball_analysis_workflow.state import (
    BaseballAnalysisWorkflowState,
    build_initial_state,
)

WORKFLOW_NAME = "baseball_analysis_workflow"


def create_baseball_analysis_workflow_graph(
    crew_id: str,
    agents: List[Dict[str, Any]],
):
    """Create the baseball analysis workflow with native LangGraph primitives."""

    workflow = StateGraph(BaseballAnalysisWorkflowState)
    workflow.add_node(
        "supervisor",
        create_agent_node(
            "supervisor",
            create_official_supervisor_graph(),
            extension=create_supervisor_extension("supervisor"),
        ),
    )
    workflow.add_node(
        "baseball_analyst",
        create_agent_node(
            "baseball_analyst",
            create_baseball_analysis_agent_graph(),
        ),
    )
    workflow.add_edge("supervisor", "baseball_analyst")
    workflow.add_edge("baseball_analyst", END)
    workflow.set_entry_point("supervisor")
    return workflow.compile(checkpointer=get_checkpointer(), store=get_store())


workflow_registry.register(
    WORKFLOW_NAME,
    create_baseball_analysis_workflow_graph,
    state_builder=build_initial_state,
)

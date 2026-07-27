"""Workflow graph for the simple supervisor collaboration pattern."""

from typing import Any, Dict, List

from app.agents.official_supervisor.graph import create_official_supervisor_graph
from langgraph.graph import END, StateGraph

from app.runtime.langgraph.checkpoint import get_checkpointer
from app.runtime.langgraph.store import get_store
from app.runtime.langgraph.adapters.agent import create_agent_node
from app.runtime.langgraph.adapters.supervisor import create_supervisor_extension
from app.workflows.registry import workflow_registry
from app.workflows.supervisor_simple.state import (
    SupervisorSimpleState,
    build_initial_state,
)

WORKFLOW_NAME = "supervisor_simple"
WORKFLOW_METADATA = {
    "entrypoint": "supervisor",
    "nodes": [
        {
            "name": "supervisor",
            "agent": "official_supervisor",
            "display_name": "监管者",
        }
    ],
    "edges": [{"from": "supervisor", "to": "END"}],
    "ui": {
        "title": "监管者对话",
        "description": "由官方监管者协调 Crew 中可用的 Agent",
        "input_placeholder": "输入需要监管者处理的任务……",
        "input_hint": "监管者会根据 Crew 配置决定是否分发任务",
    },
}


def create_supervisor_simple_graph(
    crew_id: str,
    agents: List[Dict[str, Any]],
):
    """Create the supervisor workflow with native LangGraph primitives."""

    workflow = StateGraph(SupervisorSimpleState)
    workflow.add_node(
        "supervisor",
        create_agent_node(
            "supervisor",
            create_official_supervisor_graph(),
            extension=create_supervisor_extension("supervisor"),
        ),
    )
    workflow.add_edge("supervisor", END)
    workflow.set_entry_point("supervisor")
    return workflow.compile(checkpointer=get_checkpointer(), store=get_store())


workflow_registry.register(
    WORKFLOW_NAME,
    create_supervisor_simple_graph,
    state_builder=build_initial_state,
    metadata=WORKFLOW_METADATA,
)

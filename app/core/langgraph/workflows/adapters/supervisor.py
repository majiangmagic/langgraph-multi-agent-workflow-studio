"""Workflow adapter for running the reusable supervisor agent."""

from typing import Any, Dict

from langgraph.graph import StateGraph

from app.agents.supervisor.state import DelegatedAgentState, SupervisorState
from app.core.langgraph.workflows.adapters.agent import create_agent_node


def build_workflow_agents(workflow: StateGraph) -> Dict[str, DelegatedAgentState]:
    """Build supervisor-readable agent state from workflow nodes."""

    return {
        agent_name: {
            "agent_name": agent_name,
            "messages": [],
            "status": "idle",
            "results": None,
            "tools": [],
        }
        for agent_name in workflow.nodes
    }


def create_supervisor_workflow_node(workflow: StateGraph, supervisor_graph):
    """Create a workflow node that runs the reusable supervisor agent."""

    # 下面两个函数只描述 supervisor 和 workflow state 的进出转换。
    # 真正注册到 workflow 的节点函数由 create_agent_node(...) 统一生成。
    def prepare_supervisor_state(state: Dict[str, Any]) -> SupervisorState:
        """Prepare supervisor state before running the agent graph."""
        agents = state["supervisor"]["agents"] or build_workflow_agents(workflow)
        return {
            **state["supervisor"],
            "agents": agents,
        }

    def build_supervisor_update(
        updated_supervisor_state: SupervisorState,
    ) -> Dict[str, Any]:
        """Write supervisor changes back to workflow state."""
        return {
            "supervisor": updated_supervisor_state,
        }

    return create_agent_node(
        "supervisor",
        supervisor_graph,
        prepare_agent_state=prepare_supervisor_state,
        build_workflow_update=build_supervisor_update,
    )

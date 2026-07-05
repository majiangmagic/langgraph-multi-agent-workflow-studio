"""Workflow adapter for running the reusable supervisor agent."""

from typing import Any, Dict

from langgraph.graph import StateGraph

from app.agents.supervisor.graph import create_supervisor_graph
from app.agents.supervisor.state import DelegatedAgentState, SupervisorState


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


def create_supervisor_workflow_node(workflow: StateGraph):
    """Create a workflow node that runs the reusable supervisor agent."""

    supervisor_graph = create_supervisor_graph()

    # run_supervisor 是注册到 workflow 里的节点函数。
    # 当 workflow 流转到 "supervisor" 节点时，LangGraph 会调用它。
    # 它会在运行时读取 workflow.nodes，动态生成当前工作流里的 agents。
    # 然后把 workflow 的全局 state 转成 Supervisor Agent 自己的 state，
    # 再调用 supervisor_graph.invoke(...) 执行 Supervisor Agent 内部流程。
    def run_supervisor(state: Dict[str, Any]) -> Dict[str, Any]:
        """Adapt workflow state into supervisor state and write the result back."""

        agents = state["agents"] or build_workflow_agents(workflow)
        supervisor_state: SupervisorState = {
            **state["supervisor"],
            "agents": agents,
        }
        updated_supervisor_state = supervisor_graph.invoke(supervisor_state)

        return {
            **state,
            "supervisor": updated_supervisor_state,
            "agents": updated_supervisor_state["agents"],
        }

    return run_supervisor

"""Internal shell graph for the supervisor agent."""

from langgraph.graph import END, StateGraph

from app.agents.registry import agent_registry
from app.agents.supervisor.nodes import OfficialSupervisorNode
from app.agents.supervisor.official_runtime import OfficialSupervisorRuntime
from app.agents.supervisor.state import SupervisorState


def create_graph(
    system_prompt: str | None = None,
    model_name: str | None = None,
    temperature: float = 0.2,
):
    """Create the supervisor shell that delegates internally to the official engine."""

    graph = StateGraph(SupervisorState)
    graph.add_node(
        "official_supervisor",
        OfficialSupervisorNode(
            OfficialSupervisorRuntime(
                system_prompt=system_prompt,
                model_name=model_name,
                temperature=temperature,
            )
        ),
    )
    graph.add_edge("official_supervisor", END)
    graph.set_entry_point("official_supervisor")

    return graph.compile()


create_supervisor_graph = create_graph

# Register for dynamic workflows: external workflow factories can look up
# the supervisor graph factory by the string "supervisor".
agent_registry.register("supervisor", create_graph)

"""Declarative agent graph building blocks."""

from dataclasses import dataclass, field
from typing import Any, Callable, List

from langgraph.graph import END, StateGraph


AgentNodeFactory = Callable[[], Callable[..., Any]]


@dataclass(frozen=True)
class AgentNodeSpec:
    """Declarative description of one internal agent node."""

    name: str
    factory: AgentNodeFactory


@dataclass(frozen=True)
class AgentEdgeSpec:
    """Declarative description of one directed internal agent edge."""

    source: str
    target: str


@dataclass(frozen=True)
class AgentDefinition:
    """An agent graph that can be generated from data."""

    name: str
    state_schema: Any
    entrypoint: str
    nodes: List[AgentNodeSpec]
    edges: List[AgentEdgeSpec] = field(default_factory=list)


def compile_agent_definition(definition: AgentDefinition):
    """Compile a declarative agent definition into a LangGraph."""

    graph = StateGraph(definition.state_schema)
    for node in definition.nodes:
        graph.add_node(node.name, node.factory())

    for edge in definition.edges:
        target = END if edge.target == END else edge.target
        graph.add_edge(edge.source, target)

    graph.set_entry_point(definition.entrypoint)
    return graph.compile()

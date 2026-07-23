"""Generate agent skeleton code from a JSON/YAML DSL."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


ROOT = Path(__file__).resolve().parents[1]
AGENTS_DIR = ROOT / "app" / "agents"
NODE_BLOCK_RE = re.compile(
    r"(?P<block># <agent-node name=\"(?P<name>[^\"]+)\">.*?# </agent-node>)",
    re.DOTALL,
)
DEF_RE = re.compile(r"def\s+(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)\s*\(")


@dataclass(frozen=True)
class NodeDsl:
    name: str
    handler: str


@dataclass(frozen=True)
class EdgeDsl:
    source: str
    target: str


@dataclass(frozen=True)
class AgentDsl:
    name: str
    package_segments: List[str]
    display_name: str
    state_class: str
    config: Dict[str, Any]
    state_fields: Dict[str, Dict[str, Any]]
    entrypoint: str
    nodes: List[NodeDsl]
    edges: List[EdgeDsl]


def snake_case(value: str) -> str:
    """Convert a DSL identifier to a Python-safe snake_case identifier."""

    value = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip())
    value = re.sub(r"_+", "_", value).strip("_").lower()
    if not value:
        raise ValueError("Identifier cannot be empty")
    if value[0].isdigit():
        value = f"_{value}"
    return value


def pascal_case(value: str) -> str:
    """Convert a DSL identifier to a Python class name fragment."""

    return "".join(part.capitalize() for part in snake_case(value).split("_"))


def parse_package_segments(raw_package: Any, agent_name: str) -> List[str]:
    """Parse an agent package path under app/agents."""

    if raw_package in (None, ""):
        return [agent_name]

    raw_text = str(raw_package).strip()
    raw_parts = [part for part in re.split(r"[/\\.]+", raw_text) if part.strip()]
    if (
        raw_text.startswith(("/", "\\", "."))
        or ".." in raw_text
        or re.match(r"^[a-zA-Z]:", raw_text)
    ):
        raise ValueError("agent.package must be a relative path under app/agents")

    parts = [
        snake_case(part)
        for part in raw_parts
    ]
    if not parts:
        raise ValueError("agent.package cannot be empty")
    return parts


def package_import_path(agent: AgentDsl) -> str:
    """Return the import path for this agent package."""

    return "app.agents." + ".".join(agent.package_segments)


def package_display_path(agent: AgentDsl) -> str:
    """Return the display path for generated output."""

    return "app/agents/" + "/".join(agent.package_segments)


def load_dsl(path: Path) -> Dict[str, Any]:
    """Load JSON or YAML DSL data."""

    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)

    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "YAML DSL requires PyYAML. Use .json or install PyYAML."
            ) from exc
        return yaml.safe_load(text)

    raise ValueError("DSL file must be .json, .yaml, or .yml")


def parse_nodes(raw_nodes: Any) -> List[NodeDsl]:
    """Parse nodes from either a map or a list DSL shape."""

    nodes = []
    if isinstance(raw_nodes, dict):
        items = raw_nodes.items()
    elif isinstance(raw_nodes, list):
        items = ((item["name"], item) for item in raw_nodes)
    else:
        raise ValueError("agent.nodes must be a map or a list")

    for raw_name, raw_node in items:
        name = snake_case(str(raw_name))
        node_config = raw_node or {}
        handler = snake_case(str(node_config.get("handler") or f"{name}_node"))
        nodes.append(NodeDsl(name=name, handler=handler))
    return nodes


def parse_edges(raw_edges: Any) -> List[EdgeDsl]:
    """Parse edge definitions."""

    edges = []
    for raw_edge in raw_edges or []:
        source = snake_case(str(raw_edge["from"]))
        raw_target = str(raw_edge["to"])
        target = "END" if raw_target == "END" else snake_case(raw_target)
        edges.append(EdgeDsl(source=source, target=target))
    return edges


def parse_state_fields(raw_fields: Any) -> Dict[str, Dict[str, Any]]:
    """Parse extra agent state fields."""

    fields = {}
    for raw_name, raw_field in (raw_fields or {}).items():
        fields[snake_case(str(raw_name))] = dict(raw_field or {})
    return fields


def parse_agent_dsl(data: Dict[str, Any]) -> AgentDsl:
    """Validate and normalize agent DSL."""

    if data.get("kind") != "agent":
        raise ValueError("agent DSL must set kind: agent")

    name = snake_case(str(data["name"]))
    nodes = parse_nodes(data.get("nodes"))
    if not nodes:
        raise ValueError("agent.nodes cannot be empty")

    entrypoint = snake_case(str(data.get("entrypoint") or nodes[0].name))
    node_names = {node.name for node in nodes}
    if entrypoint not in node_names:
        raise ValueError(f"entrypoint '{entrypoint}' is not defined in nodes")

    for edge in parse_edges(data.get("edges")):
        if edge.source not in node_names:
            raise ValueError(f"edge source '{edge.source}' is not defined in nodes")
        if edge.target != "END" and edge.target not in node_names:
            raise ValueError(f"edge target '{edge.target}' is not defined in nodes")

    return AgentDsl(
        name=name,
        package_segments=parse_package_segments(data.get("package"), name),
        display_name=str(data.get("display_name") or name.replace("_", " ").title()),
        state_class=str(data.get("state_schema") or f"{pascal_case(name)}State"),
        config=dict(data.get("config") or {}),
        state_fields=parse_state_fields(data.get("state")),
        entrypoint=entrypoint,
        nodes=nodes,
        edges=parse_edges(data.get("edges")),
    )


def read_existing_node_blocks(nodes_path: Path) -> Dict[str, str]:
    """Read generated node blocks keyed by stable DSL node name."""

    if not nodes_path.exists():
        return {}

    text = nodes_path.read_text(encoding="utf-8")
    return {
        match.group("name"): match.group("block")
        for match in NODE_BLOCK_RE.finditer(text)
    }


def block_handler_name(block: str, expected_handler: str) -> Optional[str]:
    """Return the DSL handler when it still exists in a preserved node block."""

    pattern = re.compile(
        rf"^(?:async\s+)?def\s+{re.escape(expected_handler)}\s*\(",
        re.MULTILINE,
    )
    return expected_handler if pattern.search(block) else None


def python_type(field: Dict[str, Any]) -> str:
    """Map simple DSL field types to Python annotations."""

    type_name = str(field.get("type") or "any").lower()
    mapping = {
        "any": "Any",
        "bool": "bool",
        "boolean": "bool",
        "dict": "Dict[str, Any]",
        "float": "float",
        "int": "int",
        "integer": "int",
        "list": "List[Any]",
        "string": "str",
        "str": "str",
    }
    annotation = mapping.get(type_name, "Any")
    if field.get("optional", True):
        return f"Optional[{annotation}]"
    return annotation


def render_init(agent: AgentDsl) -> str:
    import_path = package_import_path(agent)
    return f'''"""Public API for the {agent.name} agent."""


def __getattr__(name: str):
    if name == "create_graph":
        from {import_path}.graph import create_graph

        return create_graph
    raise AttributeError(name)


__all__ = [
    "create_graph",
]
'''


def render_graph(agent: AgentDsl) -> str:
    constant = f"{agent.name.upper()}_AGENT_NAME"
    import_path = package_import_path(agent)
    return f'''"""Graph factory for the {agent.name} agent."""

from app.agents.declarative import compile_agent_definition
from {import_path}.spec import AGENT_DEFINITION, {constant}
from app.agents.registry import agent_registry


def create_graph():
    """Create the {agent.name} agent graph."""

    return compile_agent_definition(AGENT_DEFINITION)


agent_registry.register({constant}, create_graph)
'''


def render_spec(agent: AgentDsl, handler_names: Dict[str, str]) -> str:
    constant = f"{agent.name.upper()}_AGENT_NAME"
    node_constant = f"{agent.name.upper()}_ENTRYPOINT"
    import_path = package_import_path(agent)
    imports = ", ".join(handler_names[node.name] for node in agent.nodes)
    node_factories = "\n".join(
        f'''
def create_{node.name}_node():
    """Create the {node.name} node callable."""

    return {handler_names[node.name]}
'''
        for node in agent.nodes
    )
    node_specs = "\n".join(
        f'''        AgentNodeSpec(
            name="{node.name}",
            factory=create_{node.name}_node,
        ),'''
        for node in agent.nodes
    )
    edge_specs = "\n".join(
        f'''        AgentEdgeSpec(source="{edge.source}", target={"END" if edge.target == "END" else repr(edge.target)}),'''
        for edge in agent.edges
    )
    return f'''"""Declarative spec for the {agent.name} agent."""

from langgraph.graph import END

from app.agents.declarative import AgentDefinition, AgentEdgeSpec, AgentNodeSpec
from {import_path}.nodes import {imports}
from {import_path}.state import {agent.state_class}

{constant} = "{agent.name}"
{node_constant} = "{agent.entrypoint}"

{node_factories}

AGENT_DEFINITION = AgentDefinition(
    name={constant},
    state_schema={agent.state_class},
    entrypoint={node_constant},
    nodes=[
{node_specs}
    ],
    edges=[
{edge_specs}
    ],
)
'''


def render_state(agent: AgentDsl) -> str:
    extra_fields = "\n".join(
        f"    {name}: {python_type(field)}"
        for name, field in agent.state_fields.items()
    )
    if extra_fields:
        extra_fields = "\n\n    # 下面是 DSL 声明的业务状态字段。\n" + extra_fields

    return f'''"""State schema for the {agent.name} agent."""

from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.messages import BaseMessage


class {agent.state_class}(TypedDict):
    """Runtime state for this generated agent."""

    agent_id: str
    agent_name: str
    description: Optional[str]
    system_prompt: Optional[str]
    model: Optional[str]
    temperature: float
    tools: List[Dict[str, Any]]
    messages: List[BaseMessage]
    # 本轮未经业务拆分的完整用户输入。除入口或意图解析节点外，理论上不应直接使用；
    # 下游节点应通过 Workflow DSL inputs 接收上游节点产出的结构化业务数据。
    user_input: Optional[str]
    workflow_inputs: Dict[str, Any]
    # 由平台统一注入的请求标识、会话标识和用户标识，不属于用户可配置参数。
    request_context: Dict[str, Any]{extra_fields}
'''


def render_new_node_block(agent: AgentDsl, node: NodeDsl) -> str:
    return f'''# <agent-node name="{node.name}">
# 中文注意：
# 1. 节点名 "{node.name}" 是 DSL 的稳定标识，不要随手改名。
# 2. 只要 DSL 里还保留这个节点名，刷新骨架时会保留本代码块里的业务逻辑。
# 3. 如果新 DSL 删除了这个节点名，生成器会删除整个代码块，即使里面写过业务代码。
def {node.handler}(
    state: {agent.state_class},
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """TODO: 在这里填写节点 "{node.name}" 的业务逻辑。"""

    # prompt/model/temperature 来自本地 Agent manifest 和 Workflow 节点配置，
    # 由运行时经 Workflow state 注入。
    # 这里可以读取 state["system_prompt"], state["model"], state["temperature"]。
    return {{}}
# </agent-node>'''


def render_nodes(agent: AgentDsl, existing_blocks: Dict[str, str]) -> tuple[str, Dict[str, str]]:
    handler_names = {}
    blocks = []
    for node in agent.nodes:
        existing = existing_blocks.get(node.name)
        if existing:
            handler_names[node.name] = (
                block_handler_name(existing, node.handler) or node.handler
            )
            blocks.append(existing)
        else:
            handler_names[node.name] = node.handler
            blocks.append(render_new_node_block(agent, node))

    import_path = package_import_path(agent)
    text = f'''"""Business nodes for the {agent.name} agent."""

from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from {import_path}.state import {agent.state_class}

# 本文件由 scripts/generate_agent.py 刷新骨架。
# 中文注意：
# - 只在 <agent-node ...> 代码块内部编写业务逻辑。
# - 节点名是 DSL 的稳定标识；节点名不变，刷新时保留对应代码块。
# - 新 DSL 删除某个节点名时，对应代码块会被删除，不会因为里面有人写过代码而保留。

''' + "\n\n\n".join(blocks) + "\n"
    return text, handler_names


def write_agent(agent: AgentDsl) -> None:
    """Write generated files for an agent DSL."""

    agent_dir = AGENTS_DIR.joinpath(*agent.package_segments)
    agent_dir.mkdir(parents=True, exist_ok=True)
    current_dir = AGENTS_DIR
    for segment in agent.package_segments[:-1]:
        current_dir = current_dir / segment
        init_path = current_dir / "__init__.py"
        if not init_path.exists():
            init_path.write_text('"""Agent package group."""\n', encoding="utf-8")

    nodes_path = agent_dir / "nodes.py"
    existing_blocks = read_existing_node_blocks(nodes_path)
    nodes_text, handler_names = render_nodes(agent, existing_blocks)

    (agent_dir / "__init__.py").write_text(render_init(agent), encoding="utf-8")
    (agent_dir / "graph.py").write_text(render_graph(agent), encoding="utf-8")
    (agent_dir / "spec.py").write_text(
        render_spec(agent, handler_names), encoding="utf-8"
    )
    (agent_dir / "state.py").write_text(render_state(agent), encoding="utf-8")
    nodes_path.write_text(nodes_text, encoding="utf-8")

    defaults = {
        "name": agent.name,
        "display_name": agent.display_name,
        "config": agent.config,
    }
    (agent_dir / "config_defaults.json").write_text(
        json.dumps(defaults, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dsl", type=Path, help="Path to an agent .json/.yaml DSL file")
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        agent = parse_agent_dsl(load_dsl(args.dsl))
        write_agent(agent)
    except Exception as exc:
        print(f"generate_agent failed: {exc}", file=sys.stderr)
        return 1

    print(f"Generated agent skeleton: {package_display_path(agent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

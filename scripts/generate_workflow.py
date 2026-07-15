"""Generate workflow skeleton code from a JSON/YAML DSL."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = ROOT / "app" / "core" / "langgraph" / "workflows"


@dataclass(frozen=True)
class WorkflowNodeDsl:
    name: str
    agent: str
    display_name: str
    agent_package_segments: List[str]
    state_agent: Optional[str]
    extension: Optional[str]
    on_error: str
    config: Dict[str, Any]


@dataclass(frozen=True)
class WorkflowEdgeDsl:
    source: str | tuple[str, ...]
    target: str


@dataclass(frozen=True)
class WorkflowDsl:
    name: str
    state_alias: str
    entrypoint: str
    nodes: List[WorkflowNodeDsl]
    edges: List[WorkflowEdgeDsl]
    ui: Dict[str, Any]


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
        raise ValueError("agent package must be a relative path under app/agents")

    parts = [
        snake_case(part)
        for part in raw_parts
    ]
    if not parts:
        raise ValueError("agent package cannot be empty")
    return parts


def raw_agent_looks_like_package(raw_agent: str) -> bool:
    """Return whether an agent value includes a filesystem-style package."""

    return "/" in raw_agent or "\\" in raw_agent


def agent_import_path(node: WorkflowNodeDsl) -> str:
    """Return the Python import path for a workflow node's agent."""

    return "app.agents." + ".".join(node.agent_package_segments)


def agent_graph_factory_alias(node: WorkflowNodeDsl) -> str:
    """Return a collision-resistant graph factory alias for imports."""

    return "create_" + "_".join(node.agent_package_segments) + "_graph"


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


def parse_nodes(raw_nodes: Any) -> List[WorkflowNodeDsl]:
    """Parse workflow nodes from either a map or a list DSL shape."""

    nodes = []
    if isinstance(raw_nodes, dict):
        items = raw_nodes.items()
    elif isinstance(raw_nodes, list):
        items = ((item["name"], item) for item in raw_nodes)
    else:
        raise ValueError("workflow.nodes must be a map or a list")

    for raw_name, raw_node in items:
        node_config = dict(raw_node or {})
        name = snake_case(str(raw_name))
        raw_agent = str(node_config.get("agent") or name)
        agent = (
            snake_case(re.split(r"[/\\]+", raw_agent.strip())[-1])
            if raw_agent_looks_like_package(raw_agent)
            else snake_case(raw_agent)
        )
        raw_package = (
            node_config.get("agent_package")
            or node_config.get("package")
            or (raw_agent if raw_agent_looks_like_package(raw_agent) else None)
        )
        state_agent = node_config.get("state_agent")
        extension = node_config.get("extension")
        on_error = str(node_config.get("on_error") or "fail").strip().lower()
        if on_error not in {"fail", "continue"}:
            raise ValueError(
                f"workflow node '{name}' on_error must be 'fail' or 'continue'"
            )
        nodes.append(
            WorkflowNodeDsl(
                name=name,
                agent=agent,
                display_name=str(node_config.get("display_name") or name),
                agent_package_segments=parse_package_segments(raw_package, agent),
                state_agent=snake_case(str(state_agent)) if state_agent else None,
                extension=snake_case(str(extension)) if extension else None,
                on_error=on_error,
                config=dict(node_config.get("config") or {}),
            )
        )
    return nodes


def parse_edges(raw_edges: Any) -> List[WorkflowEdgeDsl]:
    """Parse workflow edge definitions."""

    edges = []
    for raw_edge in raw_edges or []:
        raw_source = raw_edge["from"]
        source = (
            tuple(snake_case(str(item)) for item in raw_source)
            if isinstance(raw_source, list)
            else snake_case(str(raw_source))
        )
        raw_targets = raw_edge["to"]
        if not isinstance(raw_targets, list):
            raw_targets = [raw_targets]
        for raw_target in raw_targets:
            target_text = str(raw_target)
            target = "END" if target_text == "END" else snake_case(target_text)
            edges.append(WorkflowEdgeDsl(source=source, target=target))
    return edges


def normalize_ui(raw_ui: Any) -> Dict[str, Any]:
    """Validate generic workflow controls while preserving other UI metadata."""

    if raw_ui in (None, {}):
        return {}
    if not isinstance(raw_ui, dict):
        raise ValueError("workflow.ui must be a map")
    ui = dict(raw_ui)
    controls = ui.get("controls")
    if controls is None:
        return ui
    if not isinstance(controls, list):
        raise ValueError("workflow.ui.controls must be a list")

    normalized_controls = []
    seen_keys = set()
    for raw_control in controls:
        if not isinstance(raw_control, dict):
            raise ValueError("each workflow UI control must be a map")
        control = dict(raw_control)
        key = snake_case(str(control.get("key") or ""))
        if key in seen_keys:
            raise ValueError(f"duplicate workflow UI control key '{key}'")
        control_type = str(control.get("type") or "select").strip().lower()
        if control_type not in {"select", "segmented"}:
            raise ValueError(
                f"workflow UI control '{key}' has unsupported type '{control_type}'"
            )
        raw_options = control.get("options")
        if not isinstance(raw_options, list) or not raw_options:
            raise ValueError(f"workflow UI control '{key}' requires options")
        options = []
        option_values = set()
        for raw_option in raw_options:
            if not isinstance(raw_option, dict):
                raise ValueError(f"workflow UI control '{key}' options must be maps")
            value = str(raw_option.get("value") or "").strip()
            if not value or value in option_values:
                raise ValueError(
                    f"workflow UI control '{key}' has an empty or duplicate option"
                )
            option_values.add(value)
            options.append({**raw_option, "value": value})
        default = str(control.get("default") or options[0]["value"])
        if default not in option_values:
            raise ValueError(
                f"workflow UI control '{key}' default must match an option"
            )
        seen_keys.add(key)
        normalized_controls.append(
            {
                **control,
                "key": key,
                "type": control_type,
                "default": default,
                "options": options,
            }
        )
    ui["controls"] = normalized_controls
    return ui


def parse_workflow_dsl(data: Dict[str, Any]) -> WorkflowDsl:
    """Validate and normalize workflow DSL."""

    if data.get("kind") != "workflow":
        raise ValueError("workflow DSL must set kind: workflow")

    name = snake_case(str(data["name"]))
    nodes = parse_nodes(data.get("nodes"))
    if not nodes:
        raise ValueError("workflow.nodes cannot be empty")

    node_names = {node.name for node in nodes}
    entrypoint = snake_case(str(data.get("entrypoint") or nodes[0].name))
    if entrypoint not in node_names:
        raise ValueError(f"entrypoint '{entrypoint}' is not defined in nodes")

    edges = parse_edges(data.get("edges"))
    for edge in edges:
        sources = edge.source if isinstance(edge.source, tuple) else (edge.source,)
        for source in sources:
            if source not in node_names:
                raise ValueError(f"edge source '{source}' is not defined in nodes")
        if edge.target != "END" and edge.target not in node_names:
            raise ValueError(f"edge target '{edge.target}' is not defined in nodes")

    ui = normalize_ui(data.get("ui"))

    return WorkflowDsl(
        name=name,
        state_alias=str(data.get("state_alias") or f"{pascal_case(name)}State"),
        entrypoint=entrypoint,
        nodes=nodes,
        edges=edges,
        ui=ui,
    )


def render_init(workflow: WorkflowDsl) -> str:
    factory_name = f"create_{workflow.name}_graph"
    return f'''"""Public API for the {workflow.name} workflow."""

from app.core.langgraph.workflows.{workflow.name}.state import (
    {workflow.state_alias},
    build_initial_state,
)


def __getattr__(name: str):
    if name == "{factory_name}":
        from app.core.langgraph.workflows.{workflow.name}.graph import {factory_name}

        return {factory_name}
    raise AttributeError(name)


__all__ = [
    "{workflow.state_alias}",
    "build_initial_state",
    "{factory_name}",
]
'''


def render_graph(workflow: WorkflowDsl) -> str:
    factory_name = f"create_{workflow.name}_graph"
    agent_imports = render_agent_imports(workflow)
    extension_import_text, extension_by_node = extension_imports(workflow)
    node_calls = "\n".join(render_node_call(node, extension_by_node) for node in workflow.nodes)
    edge_calls = "\n".join(render_edge_call(edge) for edge in workflow.edges)
    imports = "\n".join(
        part
        for part in [
            "from langgraph.graph import END, StateGraph",
            extension_import_text,
            "from app.core.langgraph.checkpoint import get_checkpointer",
            "from app.core.langgraph.store import get_store",
            "from app.core.langgraph.workflows.adapters.agent import create_agent_node",
        ]
        if part
    )
    return f'''"""Graph factory for the {workflow.name} workflow."""

from typing import Any, Dict, List

{agent_imports}
{imports}
from app.core.langgraph.workflows.registry import workflow_registry
from app.core.langgraph.workflows.{workflow.name}.state import (
    {workflow.state_alias},
    build_initial_state,
)

WORKFLOW_NAME = "{workflow.name}"
WORKFLOW_METADATA = {render_workflow_metadata(workflow)}


def {factory_name}(
    crew_id: str,
    agents: List[Dict[str, Any]],
):
    """Create this workflow with native LangGraph primitives."""

    workflow = StateGraph({workflow.state_alias})
{node_calls}
{edge_calls}
    workflow.set_entry_point("{workflow.entrypoint}")
    return workflow.compile(checkpointer=get_checkpointer(), store=get_store())


workflow_registry.register(
    WORKFLOW_NAME,
    {factory_name},
    state_builder=build_initial_state,
    metadata=WORKFLOW_METADATA,
)
'''


def render_workflow_metadata(workflow: WorkflowDsl) -> str:
    """Render JSON-safe discovery metadata directly from the workflow DSL."""

    metadata = {
        "entrypoint": workflow.entrypoint,
        "nodes": [
            {
                "name": node.name,
                "agent": node.agent,
                "display_name": node.display_name,
                "on_error": node.on_error,
                **({"state_agent": node.state_agent} if node.state_agent else {}),
                **({"config": node.config} if node.config else {}),
            }
            for node in workflow.nodes
        ],
        "edges": [
            {
                "from": list(edge.source)
                if isinstance(edge.source, tuple)
                else edge.source,
                "to": edge.target,
            }
            for edge in workflow.edges
        ],
        "ui": workflow.ui,
    }
    return repr(metadata)


def render_edge_call(edge: WorkflowEdgeDsl) -> str:
    """Render one edge while keeping ordinary generated code easy to read."""

    source = (
        repr(list(edge.source))
        if isinstance(edge.source, tuple)
        else f'"{edge.source}"'
    )
    target = "END" if edge.target == "END" else f'"{edge.target}"'
    return f"    workflow.add_edge({source}, {target})"


def extension_imports(workflow: WorkflowDsl) -> tuple[str, Dict[str, str]]:
    """Return extension imports and factory lookup names."""

    mapping = {}
    imports = []
    for node in workflow.nodes:
        if not node.extension:
            continue
        if node.extension == "supervisor":
            imports.append(
                "from app.core.langgraph.workflows.adapters.supervisor "
                "import create_supervisor_extension"
            )
            mapping[node.name] = "create_supervisor_extension"
        elif node.extension == "supervisor_planner":
            imports.append(
                "from app.core.langgraph.workflows.adapters.supervisor "
                "import create_supervisor_planner_extension"
            )
            mapping[node.name] = "create_supervisor_planner_extension"
        elif node.extension == "pipeline_context":
            imports.append(
                "from app.core.langgraph.workflows.adapters.agent "
                "import create_pipeline_context_extension"
            )
            mapping[node.name] = "create_pipeline_context_extension"
        else:
            raise ValueError(f"Unsupported workflow node extension: {node.extension}")

    return "\n".join(sorted(set(imports))), mapping


def render_agent_imports(workflow: WorkflowDsl) -> str:
    """Render graph factory imports for all agent packages used by a workflow."""

    imports = {
        tuple(node.agent_package_segments): (
            f"from {agent_import_path(node)}.graph "
            f"import create_graph as {agent_graph_factory_alias(node)}"
        )
        for node in workflow.nodes
    }
    return "\n".join(imports[key] for key in sorted(imports))


def render_node_call(
    node: WorkflowNodeDsl,
    extension_by_node: Dict[str, str],
) -> str:
    extension = (
        f'\n            extension={extension_by_node[node.name]}("{node.name}"),'
        if node.name in extension_by_node
        else ""
    )
    error_policy = (
        "\n            continue_on_error=True,"
        if node.on_error == "continue"
        else ""
    )
    return f'''    workflow.add_node(
        "{node.name}",
        create_agent_node(
            "{node.name}",
            {agent_graph_factory_alias(node)}(),{extension}{error_policy}
        ),
    )'''


def render_state(workflow: WorkflowDsl) -> str:
    node_agents = "\n".join(
        f'    "{node.name}": "{node.state_agent or node.agent}",'
        for node in workflow.nodes
    )
    return f'''"""State helpers for the {workflow.name} workflow."""

from typing import Any, Dict, List, Optional

from langchain_core.messages import BaseMessage

from app.core.langgraph.workflows.declarative import (
    WorkflowState,
    build_workflow_initial_state,
    merge_node_states,
)

{workflow.state_alias} = WorkflowState

WORKFLOW_NAME = "{workflow.name}"
NODE_AGENTS = {{
{node_agents}
}}


def build_initial_state(
    crew_id: str,
    agents: List[Dict[str, Any]],
    user_id: str = "",
    conversation_id: str = "",
    messages: Optional[List[BaseMessage]] = None,
    user_input: Optional[str] = None,
    workflow_inputs: Optional[Dict[str, Any]] = None,
) -> WorkflowState:
    """Build initial state for this workflow definition."""

    return build_workflow_initial_state(
        workflow_name=WORKFLOW_NAME,
        node_agents=NODE_AGENTS,
        user_id=user_id,
        crew_id=crew_id,
        agents=agents,
        conversation_id=conversation_id,
        messages=messages,
        user_input=user_input,
        workflow_inputs=workflow_inputs,
    )
'''


def write_workflow(workflow: WorkflowDsl) -> None:
    """Write generated files for a workflow DSL."""

    workflow_dir = WORKFLOWS_DIR / workflow.name
    workflow_dir.mkdir(parents=True, exist_ok=True)

    (workflow_dir / "__init__.py").write_text(render_init(workflow), encoding="utf-8")
    (workflow_dir / "graph.py").write_text(render_graph(workflow), encoding="utf-8")
    (workflow_dir / "state.py").write_text(render_state(workflow), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "dsl",
        type=Path,
        help="Path to a workflow .json/.yaml DSL file",
    )
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        workflow = parse_workflow_dsl(load_dsl(args.dsl))
        write_workflow(workflow)
    except Exception as exc:
        print(f"generate_workflow failed: {exc}", file=sys.stderr)
        return 1

    print(f"Generated workflow skeleton: app/core/langgraph/workflows/{workflow.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

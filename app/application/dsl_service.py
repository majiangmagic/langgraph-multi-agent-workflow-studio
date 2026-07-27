"""Safe local persistence and generation for Agent/Workflow DSL files."""

from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Literal

from scripts.generate_agent import parse_agent_dsl, write_agent
from scripts.generate_workflow import parse_workflow_dsl, write_workflow


DslKind = Literal["agent", "workflow"]
ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = ROOT / "app" / "agents"
WORKFLOWS_DIR = ROOT / "app" / "workflows"
DSL_DIRS = {
    "agent": ROOT / "examples" / "agents",
    "workflow": ROOT / "examples" / "workflows",
}
SAFE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def validate_name(name: str) -> str:
    if not SAFE_NAME_RE.fullmatch(name):
        raise ValueError("DSL name must use lowercase letters, numbers, and underscores")
    return name


def component_dsl_path(kind: DslKind, data: dict[str, Any]) -> Path:
    """Return the canonical DSL path colocated with generated code."""

    parsed = parse_agent_dsl(data) if kind == "agent" else parse_workflow_dsl(data)
    if kind == "agent":
        return AGENTS_DIR.joinpath(*parsed.package_segments, "agent.dsl.json")
    return WORKFLOWS_DIR / parsed.name / "workflow.dsl.json"


def iter_dsl_paths(kind: DslKind):
    """Yield component definitions first, followed by ungenerated examples."""

    pattern = "**/agent.dsl.json" if kind == "agent" else "*/workflow.dsl.json"
    component_root = AGENTS_DIR if kind == "agent" else WORKFLOWS_DIR
    yield from sorted(component_root.glob(pattern))

    example_dir = DSL_DIRS[kind]
    example_dir.mkdir(parents=True, exist_ok=True)
    yield from sorted(example_dir.glob("*.json"))


def dsl_index(kind: DslKind) -> dict[str, tuple[Path, dict[str, Any]]]:
    """Index definitions by logical name, preferring colocated definitions."""

    indexed: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in iter_dsl_paths(kind):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("kind") != kind:
            continue
        name = str(data.get("name") or path.stem)
        indexed.setdefault(name, (path, data))
    return indexed


def dsl_path(kind: DslKind, name: str) -> Path:
    item = dsl_index(kind).get(validate_name(name))
    if item is None:
        raise FileNotFoundError(name)
    return item[0]


def list_dsls(kind: DslKind) -> list[dict[str, Any]]:
    items = []
    for name, (path, data) in sorted(dsl_index(kind).items()):
        relative = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
        items.append(
            {
                "kind": kind,
                "name": name,
                "display_name": (
                    data.get("display_name")
                    or (data.get("ui") or {}).get("title")
                    or name
                ),
                "path": str(relative).replace("\\", "/"),
                "generated": path.name in {"agent.dsl.json", "workflow.dsl.json"},
            }
        )
    return items


def read_dsl(kind: DslKind, name: str) -> dict[str, Any]:
    path = dsl_path(kind, name)
    if not path.exists():
        raise FileNotFoundError(name)
    return json.loads(path.read_text(encoding="utf-8"))


def validate_dsl(kind: DslKind, data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("DSL root must be an object")
    parsed = parse_agent_dsl(data) if kind == "agent" else parse_workflow_dsl(data)
    return {
        "kind": kind,
        "name": parsed.name,
        "nodes": [node.name for node in parsed.nodes],
        "entrypoint": parsed.entrypoint,
    }


def save_dsl(kind: DslKind, name: str, data: dict[str, Any]) -> dict[str, Any]:
    validation = validate_dsl(kind, data)
    if validation["name"] != validate_name(name):
        raise ValueError("URL name must match data.name")
    path = component_dsl_path(kind, data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    display_path = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
    return {**validation, "path": str(display_path).replace("\\", "/")}


def generated_paths(kind: DslKind, data: dict[str, Any]) -> list[str]:
    parsed = parse_agent_dsl(data) if kind == "agent" else parse_workflow_dsl(data)
    if kind == "agent":
        base = Path("app/agents").joinpath(*parsed.package_segments)
        names = [
            "agent.dsl.json",
            "__init__.py",
            "graph.py",
            "spec.py",
            "state.py",
            "nodes.py",
            "config_defaults.json",
        ]
    else:
        base = Path("app/workflows") / parsed.name
        names = ["workflow.dsl.json", "__init__.py", "graph.py", "state.py"]
    return [str(base / filename).replace("\\", "/") for filename in names]


def generate_dsl(kind: DslKind, data: dict[str, Any]) -> dict[str, Any]:
    validation = validate_dsl(kind, data)
    paths = generated_paths(kind, data)
    parsed = parse_agent_dsl(data) if kind == "agent" else parse_workflow_dsl(data)
    if kind == "agent":
        write_agent(parsed)
    else:
        write_workflow(parsed)

    importlib.invalidate_caches()
    if kind == "agent":
        base = "app.agents." + ".".join(parsed.package_segments)
        module_names = [f"{base}.{name}" for name in ("state", "nodes", "spec", "graph")]
    else:
        base = f"app.workflows.{parsed.name}"
        module_names = [f"{base}.state", f"{base}.graph"]

    for module_name in module_names:
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])
        else:
            importlib.import_module(module_name)

    return {**validation, "generated_files": paths, "restart_required": False}

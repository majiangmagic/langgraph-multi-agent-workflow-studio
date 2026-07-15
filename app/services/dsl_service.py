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
DSL_DIRS = {
    "agent": ROOT / "examples" / "agents",
    "workflow": ROOT / "examples" / "workflows",
}
SAFE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def validate_name(name: str) -> str:
    if not SAFE_NAME_RE.fullmatch(name):
        raise ValueError("DSL name must use lowercase letters, numbers, and underscores")
    return name


def dsl_path(kind: DslKind, name: str) -> Path:
    return DSL_DIRS[kind] / f"{validate_name(name)}.json"


def list_dsls(kind: DslKind) -> list[dict[str, Any]]:
    directory = DSL_DIRS[kind]
    directory.mkdir(parents=True, exist_ok=True)
    items = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("kind") != kind:
            continue
        items.append(
            {
                "kind": kind,
                "name": data.get("name") or path.stem,
                "display_name": (
                    data.get("display_name")
                    or (data.get("ui") or {}).get("title")
                    or data.get("name")
                    or path.stem
                ),
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
    path = dsl_path(kind, name)
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
        names = ["__init__.py", "graph.py", "spec.py", "state.py", "nodes.py", "config_defaults.json"]
    else:
        base = Path("app/core/langgraph/workflows") / parsed.name
        names = ["__init__.py", "graph.py", "state.py"]
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
        base = f"app.core.langgraph.workflows.{parsed.name}"
        module_names = [f"{base}.state", f"{base}.graph"]

    for module_name in module_names:
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])
        else:
            importlib.import_module(module_name)

    return {**validation, "generated_files": paths, "restart_required": False}

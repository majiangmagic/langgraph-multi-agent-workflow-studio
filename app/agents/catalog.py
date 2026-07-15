"""Local Agent manifests loaded from generated code packages."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any


AGENTS_DIR = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


def normalize_agent_config(data: dict[str, Any]) -> dict[str, Any]:
    """Flatten one generated config_defaults.json into runtime state config."""

    config = dict(data.get("config") or {})
    prompt = config.pop("prompt", None)
    return {
        "id": f"local:{data['name']}",
        "name": data["name"],
        "display_name": data.get("display_name") or data["name"],
        "description": data.get("description") or data.get("display_name"),
        "system_prompt": config.pop("system_prompt", None) or prompt,
        "model": config.pop("model", None),
        "temperature": config.pop("temperature", 0.2),
        "tools": config.pop("tools", []),
        "settings": config,
    }


def local_agent_catalog() -> dict[str, dict[str, Any]]:
    """Discover all generated local Agent manifests by logical name."""

    catalog: dict[str, dict[str, Any]] = {}
    for path in sorted(AGENTS_DIR.rglob("config_defaults.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Skipped invalid local Agent manifest '%s': %s", path, exc)
            continue
        name = str(data.get("name") or "").strip()
        if not name:
            continue
        catalog[name] = normalize_agent_config(data)
    return catalog


def resolve_workflow_agent_configs(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve workflow node Agent instances entirely from local manifests."""

    catalog = local_agent_catalog()
    resolved = []
    for node in metadata.get("nodes") or []:
        source_name = str(node.get("agent") or node.get("name") or "")
        base = catalog.get(source_name)
        if base is None:
            raise ValueError(f"Local agent manifest '{source_name}' is not available")

        override = dict(node.get("config") or {})
        prompt = override.pop("prompt", None)
        state_name = str(node.get("state_agent") or source_name)
        config = {
            **base,
            **override,
            "id": f"local:{source_name}:{node.get('name')}",
            "name": state_name,
            "source_agent": source_name,
        }
        if prompt is not None:
            config["system_prompt"] = prompt
        resolved.append(config)
    return resolved

"""Discover local workflow packages and trigger their registry hooks."""

import importlib
import logging
import pkgutil
from pathlib import Path

import app.workflows as workflows_package


logger = logging.getLogger(__name__)


def discover_local_workflows() -> None:
    """Import every local workflow graph that contains generated code."""

    workflows_dir = Path(next(iter(workflows_package.__path__)))
    for module in pkgutil.iter_modules(workflows_package.__path__):
        if not module.ispkg or module.name.startswith("_"):
            continue
        if not (workflows_dir / module.name / "graph.py").is_file():
            continue
        try:
            importlib.import_module(
                f"{workflows_package.__name__}.{module.name}.graph"
            )
        except ModuleNotFoundError as exc:
            logger.warning("Skipped local workflow '%s': %s", module.name, exc)

"""Registry for available LangGraph workflows."""

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from app.runtime.langgraph.common.errors import WorkflowNotFoundError

logger = logging.getLogger(__name__)

WorkflowFactory = Callable[..., object]
StateBuilder = Callable[..., Dict[str, Any]]


@dataclass(frozen=True)
class WorkflowSpec:
    """Factory functions registered for one workflow type."""

    factory: WorkflowFactory
    state_builder: Optional[StateBuilder] = None
    metadata: Dict[str, Any] | None = None


class WorkflowRegistry:
    """Small in-process registry for workflow factories."""

    def __init__(self, default_name: str = "supervisor_simple") -> None:
        self.default_name = default_name
        self._specs: Dict[str, WorkflowSpec] = {}

    def register(
        self,
        name: str,
        factory: WorkflowFactory,
        state_builder: Optional[StateBuilder] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._specs[name] = WorkflowSpec(
            factory=factory,
            state_builder=state_builder,
            metadata=metadata,
        )

    def get_spec(self, name: Optional[str] = None, *, fallback: bool = True) -> WorkflowSpec:
        workflow_name = name or self.default_name
        spec = self._specs.get(workflow_name)
        if spec is not None:
            return spec

        if fallback:
            logger.warning(
                "Unsupported workflow_type '%s'; falling back to '%s'",
                workflow_name,
                self.default_name,
            )
            default_spec = self._specs.get(self.default_name)
            if default_spec is not None:
                return default_spec

        raise WorkflowNotFoundError(f"Workflow '{workflow_name}' is not registered")

    def get(self, name: Optional[str] = None, *, fallback: bool = True) -> WorkflowFactory:
        """Return the graph factory for a registered workflow."""

        return self.get_spec(name, fallback=fallback).factory

    def get_state_builder(
        self, name: Optional[str] = None, *, fallback: bool = True
    ) -> Optional[StateBuilder]:
        """Return the initial-state builder for a registered workflow."""

        return self.get_spec(name, fallback=fallback).state_builder

    def names(self) -> list[str]:
        return sorted(self._specs)

    def get_metadata(
        self, name: Optional[str] = None, *, fallback: bool = True
    ) -> Dict[str, Any]:
        """Return JSON-safe topology and UI metadata for a workflow."""

        spec = self.get_spec(name, fallback=fallback)
        return dict(spec.metadata or {})


workflow_registry = WorkflowRegistry()

"""Generic state-driven routers used by generated workflow graphs."""

from collections.abc import Mapping
from typing import Any, Callable, Optional

from app.runtime.langgraph.events import emit_event


def read_state_path(state: Mapping[str, Any], path: str) -> Any:
    """Read a dot-separated path from nested workflow state mappings."""

    current: Any = state
    for segment in path.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            return None
        current = current[segment]
    return current


def condition_matches(actual: Any, operator: str, expected: Any) -> bool:
    """Evaluate the small, JSON-serializable condition language used by DSL edges."""

    if operator == "equals":
        return actual == expected
    if operator == "not_equals":
        return actual != expected
    if operator == "truthy":
        return bool(actual)
    if operator == "falsy":
        return not actual
    if operator == "in":
        return actual in (expected or [])
    if operator == "not_in":
        return actual not in (expected or [])
    raise ValueError(f"Unsupported workflow condition operator: {operator}")


def create_state_condition_router(
    *,
    path: str,
    operator: str = "equals",
    expected: Any = True,
    counter_path: Optional[str] = None,
    max_iterations: Optional[int] = None,
    source: str = "",
    then_target: str = "",
    otherwise_target: str = "",
    exhausted_target: str = "",
) -> Callable[[Mapping[str, Any]], str]:
    """Create a concurrency-safe router whose loop count lives in workflow state."""

    def route(state: Mapping[str, Any]) -> str:
        branch = "then"
        count = 0
        if not condition_matches(read_state_path(state, path), operator, expected):
            branch = "otherwise"
        elif counter_path and max_iterations is not None:
            raw_count = read_state_path(state, counter_path)
            try:
                count = int(raw_count or 0)
            except (TypeError, ValueError):
                count = 0
            if count >= max_iterations:
                branch = "exhausted"
        target = {
            "then": then_target,
            "otherwise": otherwise_target,
            "exhausted": exhausted_target or otherwise_target,
        }[branch]
        if source and target:
            emit_event(
                {
                    "object": "workflow.event",
                    "type": "workflow.edge.selected",
                    "from": source,
                    "to": target,
                    "branch": branch,
                    "iteration": count,
                    "max_iterations": max_iterations,
                }
            )
        return branch

    return route

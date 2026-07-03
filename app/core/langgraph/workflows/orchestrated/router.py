"""Routing helpers for the orchestrated workflow."""

from app.core.langgraph.workflows.orchestrated.state import (
    OrchestratedAction,
    OrchestratedState,
)


def route_by_action(state: OrchestratedState) -> OrchestratedAction:
    """Return the next action requested by the current state."""

    action = state.get("action")
    if action is None:
        return OrchestratedAction.CREATE_PLAN
    return action

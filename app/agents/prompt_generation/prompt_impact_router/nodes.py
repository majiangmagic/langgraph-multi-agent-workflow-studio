"""Business nodes for the prompt_impact_router agent."""

from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agents.prompt_generation.prompt_impact_router.state import PromptImpactRouterState

# <agent-node name="route_impact">
def route_impact_node(
    state: PromptImpactRouterState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Expose deterministic branch decisions from the current ImpactSet."""

    impact = state.get("impact_set") or {}
    return {
        "should_resolve_identity": bool(impact.get("identity_changed")),
        "should_resolve_visual": bool(impact.get("visual_changed")),
    }
# </agent-node>

"""Business nodes for the prompt_impact_router agent."""

from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agents.prompt_generation.prompt_impact_router.state import PromptImpactRouterState

# 本文件由 scripts/generate_agent.py 刷新骨架。
# 中文注意：
# - 只在 <agent-node ...> 代码块内部编写业务逻辑。
# - 节点名是 DSL 的稳定标识；节点名不变，刷新时保留对应代码块。
# - 新 DSL 删除某个节点名时，对应代码块会被删除，不会因为里面有人写过代码而保留。

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

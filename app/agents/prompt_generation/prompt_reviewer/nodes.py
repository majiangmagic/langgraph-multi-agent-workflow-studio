"""Business nodes for the prompt_reviewer agent."""

from typing import Any, Dict

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.agents.prompt_generation.prompt_reviewer.state import PromptReviewerState

# 本文件由 scripts/generate_agent.py 刷新骨架。
# 中文注意：
# - 只在 <agent-node ...> 代码块内部编写业务逻辑。
# - 节点名是 DSL 的稳定标识；节点名不变，刷新时保留对应代码块。
# - 新 DSL 删除某个节点名时，对应代码块会被删除，不会因为里面有人写过代码而保留。

# <agent-node name="review">
# 中文注意：
# 1. 节点名 "review" 是 DSL 的稳定标识，不要随手改名。
# 2. 只要 DSL 里还保留这个节点名，刷新骨架时会保留本代码块里的业务逻辑。
# 3. 如果新 DSL 删除了这个节点名，生成器会删除整个代码块，即使里面写过业务代码。
def review_node(
    state: PromptReviewerState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Review the prompt draft and return simple structured feedback."""

    draft = str(state.get("draft_prompt") or "")
    issues = []
    if len(draft) < 40:
        issues.append("draft_prompt_is_too_short")
    if "low quality" in draft.lower():
        issues.append("negative_terms_leaked_into_positive_prompt")

    review_result = {
        "approved": not issues,
        "issues": issues,
        "suggestions": [
            "Keep the positive prompt descriptive and visual.",
            "Keep failure terms in the negative prompt.",
        ],
    }
    return {
        "review_result": review_result,
        "messages": [
            AIMessage(
                content="Prompt review completed.",
                name="prompt_reviewer",
            )
        ],
    }
# </agent-node>

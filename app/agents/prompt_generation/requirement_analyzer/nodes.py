"""Business nodes for the prompt_requirement_analyzer agent."""

from typing import Any, Dict

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.agents.prompt_generation.requirement_analyzer.state import PromptRequirementAnalyzerState

# 本文件由 scripts/generate_agent.py 刷新骨架。
# 中文注意：
# - 只在 <agent-node ...> 代码块内部编写业务逻辑。
# - 节点名是 DSL 的稳定标识；节点名不变，刷新时保留对应代码块。
# - 新 DSL 删除某个节点名时，对应代码块会被删除，不会因为里面有人写过代码而保留。

# <agent-node name="analyze">
# 中文注意：
# 1. 节点名 "analyze" 是 DSL 的稳定标识，不要随手改名。
# 2. 只要 DSL 里还保留这个节点名，刷新骨架时会保留本代码块里的业务逻辑。
# 3. 如果新 DSL 删除了这个节点名，生成器会删除整个代码块，即使里面写过业务代码。
def analyze_node(
    state: PromptRequirementAnalyzerState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Turn the raw user request into structured prompt requirements."""

    user_input = (state.get("user_input") or "").strip()
    lowered = user_input.lower()
    target_model = "sdxl"
    if "flux" in lowered:
        target_model = "flux"
    elif "midjourney" in lowered or "--" in lowered:
        target_model = "midjourney"
    elif "pony" in lowered:
        target_model = "pony"

    style = []
    for keyword, tag in [
        ("anime", "anime"),
        ("二次元", "anime"),
        ("realistic", "realistic"),
        ("写实", "realistic"),
        ("赛博", "cyberpunk"),
        ("cyber", "cyberpunk"),
        ("水彩", "watercolor"),
        ("oil", "oil painting"),
    ]:
        if keyword in lowered and tag not in style:
            style.append(tag)

    requirements = {
        "raw_request": user_input,
        "subject": user_input or "an image subject",
        "target_model": target_model,
        "style": style or ["illustration"],
        "quality": ["high detail", "clear composition"],
        "constraints": {
            "avoid": ["low quality", "blurry", "bad anatomy"],
            "language": "english_prompt",
        },
    }
    return {
        "requirements_json": requirements,
        "messages": [
            AIMessage(
                content=f"Requirements JSON prepared for {target_model}.",
                name="prompt_requirement_analyzer",
            )
        ],
    }
# </agent-node>

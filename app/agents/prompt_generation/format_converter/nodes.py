"""Business nodes for the prompt_format_converter agent."""

from typing import Any, Dict

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.agents.prompt_generation.format_converter.state import PromptFormatConverterState

# 本文件由 scripts/generate_agent.py 刷新骨架。
# 中文注意：
# - 只在 <agent-node ...> 代码块内部编写业务逻辑。
# - 节点名是 DSL 的稳定标识；节点名不变，刷新时保留对应代码块。
# - 新 DSL 删除某个节点名时，对应代码块会被删除，不会因为里面有人写过代码而保留。

# <agent-node name="convert">
# 中文注意：
# 1. 节点名 "convert" 是 DSL 的稳定标识，不要随手改名。
# 2. 只要 DSL 里还保留这个节点名，刷新骨架时会保留本代码块里的业务逻辑。
# 3. 如果新 DSL 删除了这个节点名，生成器会删除整个代码块，即使里面写过业务代码。
def convert_node(
    state: PromptFormatConverterState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Convert the reviewed prompt into a target model format."""

    draft = str(state.get("draft_prompt") or state.get("user_input") or "")
    negative = str(state.get("negative_prompt") or "low quality, blurry, bad anatomy")
    target_model = str(state.get("target_model") or "").lower()
    if not target_model:
        requirements = state.get("requirements_json") or {}
        target_model = str(requirements.get("target_model") or "sdxl").lower()

    if target_model == "midjourney":
        formatted = f"{draft} --ar 1:1 --stylize 250"
    elif target_model == "flux":
        formatted = f"Create an image of {draft}. Use natural language detail and clean composition."
    else:
        formatted = f"Positive prompt: {draft}\nNegative prompt: {negative}"

    final_output = {
        "target_model": target_model,
        "prompt": formatted,
        "negative_prompt": negative if target_model != "midjourney" else "",
    }
    return {
        "target_model": target_model,
        "formatted_prompt": formatted,
        "final_output": final_output,
        "messages": [
            AIMessage(
                content=formatted,
                name="prompt_format_converter",
            )
        ],
    }
# </agent-node>

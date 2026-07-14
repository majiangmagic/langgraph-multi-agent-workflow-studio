"""Business nodes for the prompt_writer agent."""

from typing import Any, Dict

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.agents.prompt_generation.prompt_writer.state import PromptWriterState

# 本文件由 scripts/generate_agent.py 刷新骨架。
# 中文注意：
# - 只在 <agent-node ...> 代码块内部编写业务逻辑。
# - 节点名是 DSL 的稳定标识；节点名不变，刷新时保留对应代码块。
# - 新 DSL 删除某个节点名时，对应代码块会被删除，不会因为里面有人写过代码而保留。

# <agent-node name="write_prompt">
# 中文注意：
# 1. 节点名 "write_prompt" 是 DSL 的稳定标识，不要随手改名。
# 2. 只要 DSL 里还保留这个节点名，刷新骨架时会保留本代码块里的业务逻辑。
# 3. 如果新 DSL 删除了这个节点名，生成器会删除整个代码块，即使里面写过业务代码。
def write_prompt_node(
    state: PromptWriterState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Write the first prompt draft from requirements and tags."""

    requirements = state.get("requirements_json") or {}
    raw_request = str(requirements.get("raw_request") or state.get("user_input") or "")
    subject = str(requirements.get("subject") or raw_request or "image subject")
    quality = ", ".join(requirements.get("quality") or ["high detail"])
    tags = ", ".join(state.get("danbooru_tags") or [])

    draft = ", ".join(
        part
        for part in [
            subject,
            tags,
            quality,
            "strong composition",
            "coherent lighting",
        ]
        if part
    )
    negative = ", ".join(
        (requirements.get("constraints") or {}).get(
            "avoid", ["low quality", "blurry", "bad anatomy"]
        )
    )
    return {
        "draft_prompt": draft,
        "negative_prompt": negative,
        "messages": [
            AIMessage(
                content="Draft prompt prepared.",
                name="prompt_writer",
            )
        ],
    }
# </agent-node>

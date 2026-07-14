"""Business nodes for the prompt_danbooru_query agent."""

from typing import Any, Dict

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.agents.prompt_generation.danbooru_query.state import PromptDanbooruQueryState

# 本文件由 scripts/generate_agent.py 刷新骨架。
# 中文注意：
# - 只在 <agent-node ...> 代码块内部编写业务逻辑。
# - 节点名是 DSL 的稳定标识；节点名不变，刷新时保留对应代码块。
# - 新 DSL 删除某个节点名时，对应代码块会被删除，不会因为里面有人写过代码而保留。

# <agent-node name="query_tags">
# 中文注意：
# 1. 节点名 "query_tags" 是 DSL 的稳定标识，不要随手改名。
# 2. 只要 DSL 里还保留这个节点名，刷新骨架时会保留本代码块里的业务逻辑。
# 3. 如果新 DSL 删除了这个节点名，生成器会删除整个代码块，即使里面写过业务代码。
def query_tags_node(
    state: PromptDanbooruQueryState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Map requirements to Danbooru-style tags."""

    requirements = state.get("requirements_json") or {}
    raw_request = str(requirements.get("raw_request") or state.get("user_input") or "")
    lowered = raw_request.lower()
    tags = ["masterpiece", "best_quality"]

    style_tags = {
        "anime": ["anime_style", "detailed_eyes"],
        "realistic": ["realistic", "photorealistic"],
        "cyberpunk": ["cyberpunk", "neon_lights", "cityscape"],
        "watercolor": ["watercolor_(medium)", "soft_colors"],
        "oil painting": ["oil_painting_(medium)", "painterly"],
        "illustration": ["illustration", "detailed"],
    }
    for style in requirements.get("style") or ["illustration"]:
        for tag in style_tags.get(str(style), []):
            if tag not in tags:
                tags.append(tag)

    keyword_tags = [
        ("girl", "1girl"),
        ("boy", "1boy"),
        ("cat", "cat"),
        ("dragon", "dragon"),
        ("city", "city"),
        ("rain", "rain"),
        ("night", "night"),
        ("portrait", "portrait"),
        ("全身", "full_body"),
        ("半身", "upper_body"),
        ("夜", "night"),
        ("雨", "rain"),
        ("城市", "city"),
    ]
    for keyword, tag in keyword_tags:
        if keyword in lowered and tag not in tags:
            tags.append(tag)

    return {
        "danbooru_tags": tags,
        "tag_notes": "Local Danbooru-style tag mapping; replace this node to call a real Danbooru API.",
        "messages": [
            AIMessage(
                content=f"Prepared {len(tags)} Danbooru-style tags.",
                name="prompt_danbooru_query",
            )
        ],
    }
# </agent-node>

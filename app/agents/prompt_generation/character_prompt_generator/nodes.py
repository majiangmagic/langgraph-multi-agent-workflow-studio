"""Business nodes for the character_prompt_generator agent."""

from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agents.prompt_generation.character_prompt_generator.state import CharacterPromptGeneratorState

# 本文件由 scripts/generate_agent.py 刷新骨架。
# 中文注意：
# - 只在 <agent-node ...> 代码块内部编写业务逻辑。
# - 节点名是 DSL 的稳定标识；节点名不变，刷新时保留对应代码块。
# - 新 DSL 删除某个节点名时，对应代码块会被删除，不会因为里面有人写过代码而保留。

# <agent-node name="generate_character_prompt">
def _normalized_tag(value: Any) -> str:
    return "_".join(str(value or "").strip().lower().split())


def _identity_tags(requirements: Dict[str, Any]) -> tuple[bool, set[str]]:
    identities = requirements.get("character_identities") or []
    tags = {
        _normalized_tag(item.get("danbooru_tag"))
        for item in identities
        if isinstance(item, dict) and item.get("danbooru_tag")
    }
    return bool(identities), {tag for tag in tags if tag}


def filter_character_records(
    records: list[Dict[str, Any]], requirements: Dict[str, Any]
) -> list[Dict[str, Any]]:
    """Reject character-category tags that conflict with the identity contract."""

    has_identities, allowed_identity_tags = _identity_tags(requirements)
    if not has_identities:
        return records
    return [
        record
        for record in records
        if int(record.get("category", 0) or 0) != 4
        or _normalized_tag(record.get("name")) in allowed_identity_tags
    ]


async def generate_character_prompt_node(
    state: CharacterPromptGeneratorState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Generate character tags and include their Danbooru provenance."""

    from langchain_core.messages import AIMessage

    from app.agents.prompt_generation.danbooru import (
        lookup_for_generator,
        verified_tags_from_records,
    )

    terms, records = await lookup_for_generator(state, "character")
    records = filter_character_records(records, state.get("requirements_json") or {})
    tags = verified_tags_from_records(records)
    return {
        "character_prompt": ", ".join(tags),
        "character_tags": tags,
        "danbooru_tag_records": records,
        "danbooru_search_terms": terms,
        "messages": [
            AIMessage(
                content=f"人物提示词生成完成，采用 {len(tags)} 个 Danbooru 标签。",
                name="character_prompt_generator",
            )
        ],
    }
# </agent-node>

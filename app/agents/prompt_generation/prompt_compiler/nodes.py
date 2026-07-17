"""Business nodes for the prompt_compiler agent."""

from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agents.prompt_generation.prompt_compiler.state import PromptCompilerState

# 本文件由 scripts/generate_agent.py 刷新骨架。
# 中文注意：
# - 只在 <agent-node ...> 代码块内部编写业务逻辑。
# - 节点名是 DSL 的稳定标识；节点名不变，刷新时保留对应代码块。
# - 新 DSL 删除某个节点名时，对应代码块会被删除，不会因为里面有人写过代码而保留。

# <agent-node name="compile_prompt">
import re


def _key(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().replace("_", " ").split())


def _entries(values: Any) -> list[Dict[str, Any]]:
    result = []
    seen = set()
    for item in values or []:
        if not isinstance(item, dict):
            item = {"value": item}
        value = str(item.get("value") or "").strip()
        key = _key(value)
        if not value or key in seen:
            continue
        result.append({**item, "value": value})
        seen.add(key)
    return result


def _overlay_entry(item: Any, polarity: str) -> Dict[str, Any]:
    if isinstance(item, dict):
        return {
            **item,
            "value": str(item.get("value") or "").strip(),
            "polarity": polarity,
            "kind": str(item.get("kind") or "repair_phrase"),
            "provenance": "semantic_repair",
        }
    return {
        "value": str(item or "").strip(),
        "polarity": polarity,
        "kind": "repair_phrase",
        "source_path": "/repair",
        "provenance": "semantic_repair",
    }


def compile_prompt_node(
    state: PromptCompilerState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Compile typed resolution outputs into one traceable Prompt IR."""

    from langchain_core.messages import AIMessage

    previous_ir = state.get("previous_resolved_prompt_ir") or {}

    def current_or_previous(field: str) -> Any:
        return state.get(field) if field in state else previous_ir.get(field)

    identity_terms = _entries(current_or_previous("identity_terms"))
    atomic_terms = _entries(current_or_previous("atomic_terms"))
    relation_terms = _entries(current_or_previous("relation_terms"))
    negative_terms = _entries(current_or_previous("negative_terms"))
    positive = _entries([*identity_terms, *atomic_terms, *relation_terms])
    negative = _entries(negative_terms)
    impact = state.get("impact_set") or {}

    removed_keys = {_key(value) for value in impact.get("removed_identity_terms") or []}
    positive = [
        item
        for item in positive
        if not any(
            removed and (removed == _key(item["value"]) or removed in _key(item["value"]))
            for removed in removed_keys
        )
    ]

    document_version = int((state.get("scene_document") or {}).get("version") or 0)
    overlay = state.get("repair_overlay") or {}
    if int(overlay.get("document_version") or document_version) != document_version:
        overlay = {}
    remove_positive = {_key(value) for value in overlay.get("remove_positive") or []}
    remove_negative = {_key(value) for value in overlay.get("remove_negative") or []}
    positive = [item for item in positive if _key(item["value"]) not in remove_positive]
    negative = [item for item in negative if _key(item["value"]) not in remove_negative]
    positive = _entries(
        [
            *positive,
            *[
                _overlay_entry(item, "positive")
                for item in overlay.get("add_positive") or []
            ],
        ]
    )
    negative = _entries(
        [
            *negative,
            *[
                _overlay_entry(item, "negative")
                for item in overlay.get("add_negative") or []
            ],
        ]
    )

    records = []
    seen_records = set()
    for record in [
        *(current_or_previous("identity_tag_records") or []),
        *(current_or_previous("visual_tag_records") or []),
    ]:
        name = str(record.get("name") or "") if isinstance(record, dict) else ""
        if name and name not in seen_records:
            records.append(record)
            seen_records.add(name)
    covered_paths = list(
        dict.fromkeys(
            str(item.get("source_path") or "")
            for item in [*positive, *negative]
            if item.get("source_path")
        )
    )
    resolved_ir = {
        "document_version": document_version,
        "identity_terms": identity_terms,
        "atomic_terms": atomic_terms,
        "relation_terms": relation_terms,
        "negative_terms": negative_terms,
        "positive_terms": positive,
        "compiled_negative_terms": negative,
        "covered_paths": covered_paths,
        "identity_tag_records": list(current_or_previous("identity_tag_records") or []),
        "identity_tag_resolutions": list(current_or_previous("identity_tag_resolutions") or []),
        "identity_tag_adjudication": dict(current_or_previous("identity_tag_adjudication") or {}),
        "visual_tag_records": list(current_or_previous("visual_tag_records") or []),
        "visual_tag_resolutions": list(current_or_previous("visual_tag_resolutions") or []),
        "visual_tag_adjudication": dict(current_or_previous("visual_tag_adjudication") or {}),
        "danbooru_tag_records": records,
        "repair_overlay": dict(overlay),
    }
    from app.agents.prompt_generation.models import PromptIR

    resolved_ir = PromptIR.model_validate(resolved_ir).model_dump(mode="python")
    return {
        "resolved_prompt_ir": resolved_ir,
        "draft_prompt": ", ".join(item["value"] for item in positive),
        "negative_prompt": ", ".join(item["value"] for item in negative),
        "messages": [
            AIMessage(
                content=f"Prompt IR 编译完成，共 {len(positive)} 个正向项。",
                name="prompt_compiler",
            )
        ],
    }
# </agent-node>

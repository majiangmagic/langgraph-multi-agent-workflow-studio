"""Business nodes for the scene_document_processor agent."""

from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agents.prompt_generation.scene_document_processor.state import SceneDocumentProcessorState

# 本文件由 scripts/generate_agent.py 刷新骨架。
# 中文注意：
# - 只在 <agent-node ...> 代码块内部编写业务逻辑。
# - 节点名是 DSL 的稳定标识；节点名不变，刷新时保留对应代码块。
# - 新 DSL 删除某个节点名时，对应代码块会被删除，不会因为里面有人写过代码而保留。

# <agent-node name="apply_patch">
def apply_patch_node(
    state: SceneDocumentProcessorState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Validate and apply the proposed edit as one deterministic transaction."""

    from langchain_core.messages import AIMessage

    from app.agents.prompt_generation.domain import (
        apply_patch_proposal,
        compute_impact_set,
        empty_scene_document,
        normalize_scene_document,
        validate_patch_proposal,
    )

    previous = normalize_scene_document(
        state.get("previous_scene_document")
        or state.get("scene_document")
        or empty_scene_document()
    )
    error = ""
    clarification = state.get("clarification_request")
    try:
        proposal = validate_patch_proposal(
            state.get("patch_proposal") or {},
            int(previous.get("version") or 0),
        )
        current = apply_patch_proposal(previous, proposal)
    except Exception as exc:
        error = str(exc)
        current = previous
        clarification = clarification or (
            "The requested scene edit could not be applied safely. Please clarify it."
        )

    impact = compute_impact_set(previous, current)
    previous_ir = state.get("previous_resolved_prompt_ir") or {}
    previous_participants = previous.get("participants") or {}
    current_participants = current.get("participants") or {}
    current_names = {
        str(value or "").strip().casefold()
        for participant in current_participants.values()
        for value in (participant.get("identity") or {}).values()
        if value
    }
    removed_resolved_identities = []
    for item in previous_ir.get("identity_terms") or []:
        if not isinstance(item, dict):
            continue
        value = str(item.get("value") or "").strip()
        participant_id = str(item.get("participant_id") or "").strip()
        if not value:
            continue
        if participant_id:
            previous_identity = (
                previous_participants.get(participant_id, {}).get("identity") or {}
            )
            current_identity = (
                current_participants.get(participant_id, {}).get("identity") or {}
            )
            if participant_id not in current_participants or previous_identity != current_identity:
                removed_resolved_identities.append(value)
        elif value.casefold() not in current_names:
            removed_resolved_identities.append(value)
    impact["removed_identity_terms"] = list(
        dict.fromkeys(
            [
                *impact.get("removed_identity_terms", []),
                *removed_resolved_identities,
            ]
        )
    )
    return {
        "previous_scene_document": previous,
        "scene_document": current,
        "previous_resolved_prompt_ir": dict(previous_ir),
        "impact_set": impact,
        "patch_error": error,
        "document_valid": not error and not clarification,
        "clarification_request": clarification,
        "messages": [
            AIMessage(
                content=f"SceneDocument 已更新到版本 {current['version']}。",
                name="scene_document_processor",
            )
        ],
    }
# </agent-node>

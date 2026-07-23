"""Business nodes for the scene_document_processor agent."""

from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agents.prompt_generation.scene_document_processor.state import SceneDocumentProcessorState

# 本文件由 scripts/generate_agent.py 刷新骨架。
# 中文注意：
# - 只在 <agent-node ...> 代码块内部编写业务逻辑。
# - 节点名是 DSL 的稳定标识；节点名不变，刷新时保留对应代码块。
# - 新 DSL 删除某个节点名时，对应代码块会被删除，不会因为里面有人写过代码而保留。

# <agent-node name="prepare_context">
# 中文注意：
# 1. 节点名 "prepare_context" 是 DSL 的稳定标识，不要随手改名。
# 2. 只要 DSL 里还保留这个节点名，刷新骨架时会保留本代码块里的业务逻辑。
# 3. 如果新 DSL 删除了这个节点名，生成器会删除整个代码块，即使里面写过业务代码。
def prepare_context_node(
    state: SceneDocumentProcessorState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Normalize the document, patch and clarification inputs."""

    # prompt/model/temperature 来自本地 Agent manifest 和 Workflow 节点配置，
    # 由运行时经 Workflow state 注入。
    # 这里可以读取 state["system_prompt"], state["model"], state["temperature"]。
    from app.agents.prompt_generation.domain import (
        empty_scene_document,
        normalize_scene_document,
    )

    previous = normalize_scene_document(
        state.get("previous_scene_document")
        or state.get("scene_document")
        or empty_scene_document()
    )
    return {
        "prepared_context": {
            "previous_scene_document": previous,
            "patch_proposal": dict(state.get("patch_proposal") or {}),
            "clarification_request": state.get("clarification_request"),
            "clarification_options": list(state.get("clarification_options") or []),
        }
    }
# </agent-node>


# <agent-node name="validate_patch">
# 中文注意：
# 1. 节点名 "validate_patch" 是 DSL 的稳定标识，不要随手改名。
# 2. 只要 DSL 里还保留这个节点名，刷新骨架时会保留本代码块里的业务逻辑。
# 3. 如果新 DSL 删除了这个节点名，生成器会删除整个代码块，即使里面写过业务代码。
def validate_patch_node(
    state: SceneDocumentProcessorState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Pre-validate the patch while preserving the processor's fallback path."""

    from app.agents.prompt_generation.domain import validate_patch_proposal

    context = dict(state.get("prepared_context") or {})
    previous = context.get("previous_scene_document") or {}
    try:
        context["patch_proposal"] = validate_patch_proposal(
            context.get("patch_proposal") or {}, int(previous.get("version") or 0)
        )
        context["patch_validation_error"] = ""
    except (TypeError, ValueError) as exc:
        context["patch_validation_error"] = str(exc)
    return {"prepared_context": context}
# </agent-node>


# <agent-node name="apply_patch">
import hashlib


def _constraint_id(polarity: str, value: str) -> str:
    normalized = " ".join(value.strip().casefold().replace("_", " ").split())
    payload = f"{polarity}|{normalized}".encode("utf-8")
    return "con_" + hashlib.sha1(payload).hexdigest()[:16]


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

    state = {**state, **dict(state.get("prepared_context") or {})}
    previous = normalize_scene_document(
        state.get("previous_scene_document")
        or state.get("scene_document")
        or empty_scene_document()
    )
    error = ""
    clarification = state.get("clarification_request")
    clarification_options = list(state.get("clarification_options") or [])
    proposal = {"rejected_enrichment_ids": []}
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
    previous_ir = dict(state.get("previous_resolved_prompt_ir") or {})
    overlay = dict(previous_ir.get("enrichment_overlay") or {})
    overlay_entries = {
        key: dict(value)
        for key, value in (overlay.get("entries") or {}).items()
        if isinstance(value, dict)
    }
    rejected_enrichment_ids = list(proposal.get("rejected_enrichment_ids") or [])
    for enrichment_id in rejected_enrichment_ids:
        if enrichment_id not in overlay_entries:
            continue
        overlay_entries[enrichment_id]["status"] = "rejected"
        overlay_entries[enrichment_id]["rejected_by"] = "user"
        overlay_entries[enrichment_id]["rejected_at_document_version"] = int(
            current.get("version") or previous.get("version") or 0
        )
    if overlay_entries:
        previous_ir["enrichment_overlay"] = {
            "version": int(overlay.get("version") or 0) + bool(rejected_enrichment_ids),
            "entries": overlay_entries,
        }
    constraint_overlay = dict(previous_ir.get("constraint_overlay") or {})
    constraint_entries = {
        key: dict(value)
        for key, value in (constraint_overlay.get("entries") or {}).items()
        if isinstance(value, dict)
    }
    constraints_changed = False
    for polarity, values in (
        ("positive", proposal.get("add_positive_constraints") or []),
        ("negative", proposal.get("add_negative_constraints") or []),
    ):
        for value in values:
            text = str(value or "").strip()
            if not text:
                continue
            constraint_id = _constraint_id(polarity, text)
            constraint_entries[constraint_id] = {
                "id": constraint_id,
                "value": text,
                "polarity": polarity,
                "status": "active",
                "source": "user_feedback",
                "created_document_version": int(current.get("version") or 0),
            }
            constraints_changed = True
    for constraint_id in proposal.get("removed_constraint_ids") or []:
        if constraint_id in constraint_entries:
            constraint_entries[constraint_id]["status"] = "removed"
            constraint_entries[constraint_id]["removed_by"] = "user"
            constraints_changed = True
    if constraint_entries:
        previous_ir["constraint_overlay"] = {
            "version": int(constraint_overlay.get("version") or 0)
            + bool(constraints_changed),
            "entries": constraint_entries,
        }
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
    impact["rejected_enrichment_ids"] = rejected_enrichment_ids
    if rejected_enrichment_ids:
        impact["visual_changed"] = True
    impact["constraints_changed"] = constraints_changed
    if constraints_changed:
        impact["visual_changed"] = True
    return {
        "previous_scene_document": previous,
        "scene_document": current,
        "previous_resolved_prompt_ir": dict(previous_ir),
        "impact_set": impact,
        "patch_error": error,
        "document_valid": not error and not clarification,
        "clarification_request": clarification,
        "clarification_options": clarification_options,
        "messages": [
            AIMessage(
                content=f"SceneDocument 已更新到版本 {current['version']}。",
                name="scene_document_processor",
            )
        ],
    }
# </agent-node>


# <agent-node name="validate_document">
# 中文注意：
# 1. 节点名 "validate_document" 是 DSL 的稳定标识，不要随手改名。
# 2. 只要 DSL 里还保留这个节点名，刷新骨架时会保留本代码块里的业务逻辑。
# 3. 如果新 DSL 删除了这个节点名，生成器会删除整个代码块，即使里面写过业务代码。
def validate_document_node(
    state: SceneDocumentProcessorState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Normalize the committed document and verify processor output types."""

    from app.agents.prompt_generation.domain import normalize_scene_document

    if not isinstance(state.get("impact_set"), dict):
        raise ValueError("scene document processor did not produce an impact_set")
    if not isinstance(state.get("document_valid"), bool):
        raise ValueError("scene document processor did not produce document_valid")
    return {"scene_document": normalize_scene_document(state.get("scene_document") or {})}
# </agent-node>


# <agent-node name="build_agent_contexts">
# 中文注意：
# 1. 节点名 "build_agent_contexts" 是 DSL 的稳定标识，不要随手改名。
# 2. 只要 DSL 里还保留这个节点名，刷新骨架时会保留本代码块里的业务逻辑。
# 3. 如果新 DSL 删除了这个节点名，生成器会删除整个代码块，即使里面写过业务代码。
def build_agent_contexts_node(
    state: SceneDocumentProcessorState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """按下游职责切割 SceneDocument，避免各 Agent 重新解释完整输入。"""

    from copy import deepcopy

    document = dict(state.get("scene_document") or {})
    participants = document.get("participants") or {}
    identity_context = {
        "version": int(document.get("version") or 0),
        "participants": {
            participant_id: {
                "type": participant.get("type"),
                "identity": deepcopy(participant.get("identity") or {}),
            }
            for participant_id, participant in participants.items()
            if isinstance(participant, dict)
        },
    }
    visual_context = {
        key: deepcopy(document.get(key))
        for key in (
            "version",
            "environment",
            "composition",
            "relations",
            "requirements",
            "revision",
        )
    }
    visual_context["participants"] = {
        participant_id: {
            key: deepcopy(value)
            for key, value in participant.items()
            if key != "identity"
        }
        for participant_id, participant in participants.items()
        if isinstance(participant, dict)
    }
    return {
        "identity_context": identity_context,
        "visual_context": visual_context,
    }
# </agent-node>

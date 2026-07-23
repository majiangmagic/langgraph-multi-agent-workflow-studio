"""Business nodes for the character_identity_resolver agent."""

from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agents.prompt_generation.character_identity_resolver.state import CharacterIdentityResolverState

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
    state: CharacterIdentityResolverState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Isolate identity resolution inputs from workflow state."""

    # prompt/model/temperature 来自本地 Agent manifest 和 Workflow 节点配置，
    # 由运行时经 Workflow state 注入。
    # 这里可以读取 state["system_prompt"], state["model"], state["temperature"]。
    return {
        "prepared_context": {
            "identity_context": dict(state.get("identity_context") or {}),
            "previous_resolved_prompt_ir": dict(
                state.get("previous_resolved_prompt_ir") or {}
            ),
            "impact_set": dict(state.get("impact_set") or {}),
        }
    }
# </agent-node>


# <agent-node name="collect_identities">
# 中文注意：
# 1. 节点名 "collect_identities" 是 DSL 的稳定标识，不要随手改名。
# 2. 只要 DSL 里还保留这个节点名，刷新骨架时会保留本代码块里的业务逻辑。
# 3. 如果新 DSL 删除了这个节点名，生成器会删除整个代码块，即使里面写过业务代码。
def collect_identities_node(
    state: CharacterIdentityResolverState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Collect participants that have an explicit identity to resolve."""

    context = dict(state.get("prepared_context") or {})
    participants = (context.get("identity_context") or {}).get("participants") or {}
    impact = context.get("impact_set") or {}
    changed_ids = set(impact.get("identity_changed_participant_ids") or [])
    incremental = bool(context.get("previous_resolved_prompt_ir")) and bool(changed_ids)
    context["identity_candidates"] = [
        {
            "participant_id": participant_id,
            "input_name": str((item.get("identity") or {}).get("input_name") or "").strip(),
        }
        for participant_id, item in participants.items()
        if isinstance(item, dict)
        and item.get("type") == "named_character"
        and str((item.get("identity") or {}).get("input_name") or "").strip()
        and (not incremental or participant_id in changed_ids)
    ]
    return {"prepared_context": context}
# </agent-node>


# <agent-node name="resolve_identities">
import json
import re


def _parse_identities(text: str) -> list[Dict[str, Any]]:
    from app.agents.prompt_generation.models import IdentityExtraction

    match = re.search(r"\{[\s\S]*\}", text.strip())
    parsed = IdentityExtraction.model_validate_json(match.group(0) if match else text)
    return [item.model_dump(mode="python") for item in parsed.identities]


def _parse_decisions(text: str) -> list[Dict[str, Any]]:
    from app.agents.prompt_generation.models import IdentityAdjudication

    match = re.search(r"\{[\s\S]*\}", text.strip())
    parsed = IdentityAdjudication.model_validate_json(match.group(0) if match else text)
    return [item.model_dump(mode="python") for item in parsed.decisions]


def _tag(value: Any) -> str:
    return re.sub(r"\s+", "_", str(value or "").strip().lower())


async def resolve_identities_node(
    state: CharacterIdentityResolverState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Resolve named participants and verify their character-category tags."""

    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    from app.agents.prompt_generation.danbooru import resolve_tag_candidates, unique_text
    from app.services.ai_provider import AIProvider, ai_provider

    state = {**state, **dict(state.get("prepared_context") or {})}
    document = state.get("identity_context") or {}
    previous_ir = state.get("previous_resolved_prompt_ir") or {}
    impact = state.get("impact_set") or {}
    participants = document.get("participants") or {}
    if not impact.get("identity_changed") and previous_ir.get("identity_terms") is not None:
        return {
            "identity_terms": list(previous_ir.get("identity_terms") or []),
            "identity_tag_records": list(previous_ir.get("identity_tag_records") or []),
            "identity_tag_resolutions": list(previous_ir.get("identity_tag_resolutions") or []),
            "identity_tag_adjudication": dict(previous_ir.get("identity_tag_adjudication") or {}),
            "identity_search_terms": list(previous_ir.get("identity_search_terms") or []),
            "messages": [
                AIMessage(content="角色身份未变化，已复用上一版本解析。", name="character_identity_resolver")
            ],
        }

    changed_ids = set(impact.get("identity_changed_participant_ids") or [])
    deleted_ids = set(impact.get("identity_deleted_participant_ids") or [])
    incremental = bool(previous_ir) and bool(changed_ids)
    named = list(state.get("identity_candidates") or [
        {
            "participant_id": participant_id,
            "input_name": str((participant.get("identity") or {}).get("input_name") or "").strip(),
        }
        for participant_id, participant in participants.items()
        if participant.get("type") == "named_character"
        and str((participant.get("identity") or {}).get("input_name") or "").strip()
        and (not incremental or participant_id in changed_ids)
    ])
    resolved: list[Dict[str, Any]] = []
    model = None
    if named:
        system_prompt = (
            f"{state.get('system_prompt') or ''}\n\n"
            "Return one JSON object with identities. Each item must contain "
            "participant_id, input_name, canonical_name, series and "
            "danbooru_tag_candidates. Candidates must be plausible exact Danbooru "
            "character tags, including an unqualified tag when that is the real tag. "
            "Never replace a character with a similar identity. If uncertain, keep "
            "the canonical name useful for lookup and return an empty candidate list."
        )
        try:
            model = ai_provider.get_model(
                model_name=state.get("model") or AIProvider.DEFAULT_MODEL,
                temperature=state.get("temperature", 0.1),
            )
            response = await model.ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=json.dumps(named, ensure_ascii=False)),
                ]
            )
            resolved = _parse_identities(str(response.content))
        except Exception:
            resolved = []

    by_id = {str(item.get("participant_id") or ""): item for item in resolved}
    candidates: list[str] = []
    for item in named:
        result = by_id.get(item["participant_id"], {})
        candidates.extend(result.get("danbooru_tag_candidates") or [])
        canonical = str(result.get("canonical_name") or "").strip()
        if canonical:
            candidates.append(canonical)
    candidates = unique_text(candidates, limit=24)
    try:
        resolutions = await resolve_tag_candidates(candidates, limit=24)
    except Exception:
        resolutions = []
    resolutions = [{**item, "phase": "initial"} for item in resolutions]

    initial_by_input = {
        _tag(item.get("normalized_input")): item for item in resolutions
    }
    uncertain_identities = []
    for item in named:
        participant_id = item["participant_id"]
        result = by_id.get(participant_id, {})
        item_candidates = unique_text(
            [
                *(result.get("danbooru_tag_candidates") or []),
                result.get("canonical_name"),
            ],
            limit=8,
        )
        item_resolutions = [
            initial_by_input[_tag(value)]
            for value in item_candidates
            if _tag(value) in initial_by_input
        ]
        character_matches = [
            resolution
            for resolution in item_resolutions
            if resolution.get("name") and int(resolution.get("category") or 0) == 4
        ]
        statuses = {str(value.get("status") or "") for value in item_resolutions}
        if "unavailable" in statuses and not character_matches:
            continue
        if not character_matches or len(character_matches) > 1 or "corrected" in statuses:
            uncertain_identities.append(
                {
                    "participant_id": participant_id,
                    "input_name": item["input_name"],
                    "canonical_name": str(result.get("canonical_name") or ""),
                    "series": str(result.get("series") or ""),
                    "candidates": item_candidates,
                    "resolutions": item_resolutions,
                }
            )

    decisions: list[Dict[str, Any]] = []
    adjudication_error = ""
    if uncertain_identities and model is not None:
        adjudication_prompt = """You adjudicate uncertain named-character tag mappings.
For each participant return participant_id, action, selected_tag, retry_candidates,
canonical_name and reason. action is select, retry or name_only. Never substitute a
similar character. selected_tag must match the exact identity and series. New tag
candidates are proposals only and will be verified again as Danbooru character
tags. If identity cannot be established, use name_only. Return only
{"decisions": [...]}.
"""
        try:
            response = await model.ainvoke(
                [
                    SystemMessage(content=adjudication_prompt),
                    HumanMessage(content=json.dumps(uncertain_identities, ensure_ascii=False)),
                ]
            )
            decisions = _parse_decisions(str(response.content))
        except Exception as exc:
            adjudication_error = str(exc)

    retry_candidates = unique_text(
        [
            candidate
            for decision in decisions
            for candidate in (decision.get("retry_candidates") or [])
        ],
        limit=16,
    )
    retry_resolutions = []
    if retry_candidates:
        try:
            retry_resolutions = await resolve_tag_candidates(retry_candidates, limit=16)
        except Exception as exc:
            adjudication_error = adjudication_error or str(exc)
    retry_resolutions = [
        {**item, "phase": "adjudication_retry"} for item in retry_resolutions
    ]
    resolutions = [*resolutions, *retry_resolutions]
    records = [item for item in resolutions if item.get("name")]
    character_records = [
        record for record in records if int(record.get("category") or 0) == 4
    ]
    resolved_by_input = {
        _tag(record.get("normalized_input")): record
        for record in character_records
    }
    resolved_by_name = {
        _tag(record.get("name")): record for record in character_records
    }
    decisions_by_participant = {
        str(item.get("participant_id") or ""): item
        for item in decisions
        if item.get("participant_id")
    }
    terms: list[Dict[str, Any]] = []
    for item in named:
        participant_id = item["participant_id"]
        result = by_id.get(participant_id, {})
        item_candidates = unique_text(
            [
                *(result.get("danbooru_tag_candidates") or []),
                result.get("canonical_name"),
            ],
            limit=8,
        )
        selected = next(
            (
                _tag(resolved_by_input[_tag(value)].get("name"))
                for value in item_candidates
                if _tag(value) in resolved_by_input
            ),
            "",
        )
        decision = decisions_by_participant.get(participant_id)
        if decision:
            action = str(decision.get("action") or "").strip().lower()
            requested = _tag(decision.get("selected_tag"))
            selected_record = resolved_by_name.get(requested) or resolved_by_input.get(requested)
            if action == "name_only":
                selected = ""
            elif selected_record:
                selected = _tag(selected_record.get("name"))
            elif action == "retry":
                selected = next(
                    (
                        _tag(resolved_by_input[_tag(value)].get("name"))
                        for value in decision.get("retry_candidates") or []
                        if _tag(value) in resolved_by_input
                    ),
                    selected,
                )
        if selected:
            value = selected
            kind = "verified_identity_tag"
            provenance = "danbooru"
        else:
            value = str(
                (decision or {}).get("canonical_name")
                or result.get("canonical_name")
                or item.get("input_name")
                or ""
            ).strip()
            kind = "identity_phrase"
            provenance = "model_unverified"
        if value:
            terms.append(
                {
                    "value": value,
                    "kind": kind,
                    "polarity": "positive",
                    "source_path": f"/participants/{participant_id}/identity",
                    "participant_id": participant_id,
                    "provenance": provenance,
                }
            )
    if incremental:
        terms = [
            *[
                item
                for item in previous_ir.get("identity_terms") or []
                if isinstance(item, dict)
                and item.get("participant_id") not in changed_ids | deleted_ids
            ],
            *terms,
        ]
    return {
        "identity_terms": terms,
        "identity_tag_records": character_records,
        "identity_tag_resolutions": resolutions,
        "identity_tag_adjudication": {
            "triggered": bool(uncertain_identities),
            "issues": uncertain_identities,
            "decisions": decisions,
            "retry_candidates": retry_candidates,
            "error": adjudication_error,
        },
        "identity_search_terms": candidates,
        "messages": [
            AIMessage(
                content=f"已解析 {len(named)} 个具名角色，验证 {len(character_records)} 个角色标签。",
                name="character_identity_resolver",
            )
        ],
    }
# </agent-node>


# <agent-node name="validate_identity_result">
# 中文注意：
# 1. 节点名 "validate_identity_result" 是 DSL 的稳定标识，不要随手改名。
# 2. 只要 DSL 里还保留这个节点名，刷新骨架时会保留本代码块里的业务逻辑。
# 3. 如果新 DSL 删除了这个节点名，生成器会删除整个代码块，即使里面写过业务代码。
def validate_identity_result_node(
    state: CharacterIdentityResolverState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Validate the identity resolver's public output contract."""

    list_fields = ("identity_terms", "identity_tag_records", "identity_tag_resolutions")
    for field in list_fields:
        if not isinstance(state.get(field), list):
            raise ValueError(f"identity resolver did not produce {field}")
    if not isinstance(state.get("identity_tag_adjudication"), dict):
        raise ValueError("identity resolver did not produce identity_tag_adjudication")
    return {
        **{field: list(state.get(field) or []) for field in list_fields},
        "identity_tag_adjudication": dict(state.get("identity_tag_adjudication") or {}),
    }
# </agent-node>

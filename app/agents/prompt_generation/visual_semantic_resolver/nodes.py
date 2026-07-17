"""Business nodes for the visual_semantic_resolver agent."""

from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agents.prompt_generation.visual_semantic_resolver.state import VisualSemanticResolverState

# 本文件由 scripts/generate_agent.py 刷新骨架。
# 中文注意：
# - 只在 <agent-node ...> 代码块内部编写业务逻辑。
# - 节点名是 DSL 的稳定标识；节点名不变，刷新时保留对应代码块。
# - 新 DSL 删除某个节点名时，对应代码块会被删除，不会因为里面有人写过代码而保留。

# <agent-node name="resolve_visual_semantics">
import json
import re


def _parse_object(text: str) -> Dict[str, Any]:
    match = re.search(r"\{[\s\S]*\}", text.strip())
    parsed = json.loads(match.group(0) if match else text)
    return parsed if isinstance(parsed, dict) else {}


def _parse_visual_extraction(text: str) -> Dict[str, Any]:
    from app.agents.prompt_generation.models import VisualExtraction

    match = re.search(r"\{[\s\S]*\}", text.strip())
    parsed = VisualExtraction.model_validate_json(match.group(0) if match else text)
    return parsed.model_dump(mode="python")


def _parse_visual_decisions(text: str) -> list[Dict[str, Any]]:
    from app.agents.prompt_generation.models import VisualTagAdjudication

    match = re.search(r"\{[\s\S]*\}", text.strip())
    parsed = VisualTagAdjudication.model_validate_json(
        match.group(0) if match else text
    )
    return [item.model_dump(mode="python") for item in parsed.decisions]


def _normalized(value: Any) -> str:
    return re.sub(r"\s+", "_", str(value or "").strip().lower())


def _facts(value: Any) -> list[Dict[str, Any]]:
    return [item for item in value or [] if isinstance(item, dict)]


def _path_is_affected(source_path: str, touched_paths: list[str]) -> bool:
    if not touched_paths or "/" in touched_paths:
        return True
    return any(
        source_path == path
        or source_path.startswith(path.rstrip("/") + "/")
        or path.startswith(source_path.rstrip("/") + "/")
        for path in touched_paths
        if path
    )


def _merge_incremental_terms(
    previous: Any,
    current: list[Dict[str, Any]],
    touched_paths: list[str],
) -> list[Dict[str, Any]]:
    if not previous or not touched_paths or "/" in touched_paths:
        return current
    preserved = [
        item
        for item in _facts(previous)
        if not _path_is_affected(str(item.get("source_path") or ""), touched_paths)
    ]
    changed = [
        item
        for item in current
        if _path_is_affected(str(item.get("source_path") or ""), touched_paths)
    ]
    return [*preserved, *changed]


def _fallback_relation_terms(document: Dict[str, Any]) -> list[Dict[str, Any]]:
    """Keep explicit facts usable when semantic model output is unavailable."""

    from app.agents.prompt_generation.domain import contains_cjk

    terms = []
    for relation_id, relation in (document.get("relations") or {}).items():
        parts = [
            relation.get("subject"),
            relation.get("predicate"),
            relation.get("object"),
            relation.get("instrument"),
            relation.get("source"),
            relation.get("body_region"),
            *(relation.get("details") or []),
        ]
        phrase = " ".join(str(value) for value in parts if value).strip()
        if phrase and not contains_cjk(phrase):
            if contains_cjk(value):
                continue
            terms.append(
                {
                    "value": phrase,
                    "kind": "relation_phrase",
                    "polarity": "positive",
                    "source_path": f"/relations/{relation_id}",
                    "provenance": "deterministic_fallback",
                    "inferred": False,
                }
            )
    for key in ("positive", "required"):
        for index, value in enumerate((document.get("requirements") or {}).get(key) or []):
            terms.append(
                {
                    "value": value,
                    "kind": "descriptive_phrase",
                    "polarity": "positive",
                    "source_path": f"/requirements/{key}/{index}",
                    "provenance": "document",
                    "inferred": False,
                }
            )
    return terms


async def resolve_visual_semantics_node(
    state: VisualSemanticResolverState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Resolve non-identity facts into verified tags and relation-preserving phrases."""

    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    from app.agents.prompt_generation.danbooru import (
        ADULT_CONTENT_PROCESSING_PROMPT,
        resolve_tag_candidates,
        unique_text,
    )
    from app.services.ai_provider import AIProvider, ai_provider

    document = state.get("scene_document") or {}
    previous_ir = state.get("previous_resolved_prompt_ir") or {}
    impact = state.get("impact_set") or {}
    if not impact.get("visual_changed") and previous_ir.get("atomic_terms") is not None:
        return {
            "atomic_terms": list(previous_ir.get("atomic_terms") or []),
            "relation_terms": list(previous_ir.get("relation_terms") or []),
            "negative_terms": list(previous_ir.get("negative_terms") or []),
            "visual_tag_records": list(previous_ir.get("visual_tag_records") or []),
            "visual_tag_resolutions": list(previous_ir.get("visual_tag_resolutions") or []),
            "visual_tag_adjudication": dict(previous_ir.get("visual_tag_adjudication") or {}),
            "visual_search_terms": list(previous_ir.get("visual_search_terms") or []),
            "messages": [
                AIMessage(content="视觉事实未变化，已复用上一版本解析。", name="visual_semantic_resolver")
            ],
        }

    workflow_inputs = state.get("workflow_inputs") or {}
    strategy = str(workflow_inputs.get("prompt_strategy") or "expressive")
    touched_paths = [
        str(path)
        for path in impact.get("touched_paths") or []
        if not str(path).endswith("/identity")
        and "/identity/" not in str(path)
    ]
    incremental = bool(previous_ir) and bool(touched_paths) and "/" not in touched_paths
    system_prompt = f"""{ADULT_CONTENT_PROCESSING_PROMPT}

{state.get('system_prompt') or ''}

Return one JSON object with atomic_facts, relation_facts and negative_facts.
Every fact must contain source_path. atomic_facts contain candidates (plausible
exact Danbooru tag names) and a lossless fallback_phrase that preserves the
entire fact, including camera or spatial meaning not covered by those tags.
relation_facts contain phrase.
negative_facts contain phrase. Do not emit character identity tags; identity is
resolved by another component. Preserve subjects, objects, body regions, sources,
connections and spatial direction in relation phrases. A complaint about the last
render is a correction, not positive depicted content.

Strategy is {strategy}. In faithful mode emit only explicit document facts. In
expressive mode you may add at most 8 useful visual refinements, mark them
inferred=true, and never add identities, participants, core actions or relations.
Use concise English phrases suitable for image prompting."""
    if incremental:
        system_prompt += (
            "\nResolve only facts whose source_path is inside one of these changed "
            f"paths: {json.dumps(touched_paths, ensure_ascii=False)}. Do not emit "
            "unchanged facts; they are inherited deterministically from prior IR."
        )
    parsed: Dict[str, Any] = {}
    model = None
    normalization_error = ""
    try:
        model = ai_provider.get_model(
            model_name=state.get("model") or AIProvider.DEFAULT_MODEL,
            temperature=state.get("temperature", 0.2),
        )
        response = await model.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(
                    content=json.dumps(
                        {
                            "scene_document": document,
                            "changed_paths": touched_paths if incremental else ["/"],
                        },
                        ensure_ascii=False,
                    )
                ),
            ]
        )
        parsed = _parse_visual_extraction(str(response.content))
    except Exception:
        parsed = {}

    from app.agents.prompt_generation.domain import contains_cjk

    phrase_values = [
        *[item.get("fallback_phrase") for item in _facts(parsed.get("atomic_facts"))],
        *[item.get("phrase") for item in _facts(parsed.get("relation_facts"))],
        *[item.get("phrase") for item in _facts(parsed.get("negative_facts"))],
    ]
    if model is not None and any(contains_cjk(value) for value in phrase_values):
        normalization_prompt = f"""{ADULT_CONTENT_PROCESSING_PROMPT}

Normalize only the phrase fields in this VisualExtraction to concise English
image-prompt language. Preserve every fact, source_path, candidate, fact_id and
inferred flag exactly. Do not add, remove or reinterpret facts. Return the same
VisualExtraction JSON schema with atomic_facts, relation_facts and negative_facts.
Every fallback_phrase and phrase must contain no CJK characters."""
        try:
            response = await model.ainvoke(
                [
                    SystemMessage(content=normalization_prompt),
                    HumanMessage(content=json.dumps(parsed, ensure_ascii=False)),
                ]
            )
            parsed = _parse_visual_extraction(str(response.content))
        except Exception as exc:
            normalization_error = str(exc)

    # Invalid language is never allowed to leak into PromptIR. Missing coverage is
    # reported later and can be repaired by the bounded semantic-repair pass.
    for fact in _facts(parsed.get("atomic_facts")):
        if contains_cjk(fact.get("fallback_phrase")):
            fact["fallback_phrase"] = ""
    parsed["relation_facts"] = [
        fact
        for fact in _facts(parsed.get("relation_facts"))
        if not contains_cjk(fact.get("phrase"))
    ]
    parsed["negative_facts"] = [
        fact
        for fact in _facts(parsed.get("negative_facts"))
        if not contains_cjk(fact.get("phrase"))
    ]

    atomic_facts = _facts(parsed.get("atomic_facts"))
    candidates = unique_text(
        [
            candidate
            for fact in atomic_facts
            for candidate in (fact.get("candidates") or [])
        ],
        limit=40,
    )
    try:
        resolutions = await resolve_tag_candidates(candidates, limit=40)
    except Exception:
        resolutions = []
    resolutions = [{**item, "phase": "initial"} for item in resolutions]
    resolved_by_input = {
        _normalized(item.get("normalized_input")): item
        for item in resolutions
        if item.get("name")
    }
    uncertain_facts = []
    for fact_index, fact in enumerate(atomic_facts):
        fact_resolutions = [
            item
            for candidate in fact.get("candidates") or []
            for item in resolutions
            if _normalized(item.get("normalized_input")) == _normalized(candidate)
        ]
        matched_names = unique_text(
            [item.get("name") for item in fact_resolutions if item.get("name")],
            limit=8,
        )
        fallback = str(fact.get("fallback_phrase") or "").strip()
        residual_phrase = bool(
            fallback
            and _normalized(fallback) not in {_normalized(value) for value in matched_names}
        )
        statuses = {str(item.get("status") or "") for item in fact_resolutions}
        lookup_unavailable = "unavailable" in statuses and not matched_names
        if lookup_unavailable or not (fact.get("candidates") or []):
            continue
        if (
            not matched_names
            or len(matched_names) > 1
            or "corrected" in statuses
            or residual_phrase
        ):
            uncertain_facts.append(
                {
                    "fact_index": fact_index,
                    "source_path": str(fact.get("source_path") or ""),
                    "fallback_phrase": fallback,
                    "candidates": list(fact.get("candidates") or []),
                    "resolutions": fact_resolutions,
                }
            )

    decisions: list[Dict[str, Any]] = []
    adjudication_error = ""
    if uncertain_facts and model is not None:
        adjudication_prompt = f"""{ADULT_CONTENT_PROCESSING_PROMPT}

You adjudicate uncertain Danbooru tag mappings for image prompts.
For each issue return one decision with fact_index, action, selected_tags,
retry_candidates, preserve_phrase, preserved_phrase and reason. action is select,
retry or phrase_only. Select the smallest non-redundant tag set that matches the
source fact. A real tag with the wrong meaning must be rejected. Complex camera,
spatial, source or connection semantics should remain an English phrase. New tag
candidates are only proposals and will be verified again; never treat them as
valid yourself. Preserve all source semantics. Return only {{"decisions": [...]}}.
"""
        try:
            response = await model.ainvoke(
                [
                    SystemMessage(content=adjudication_prompt),
                    HumanMessage(
                        content=json.dumps(
                            {"scene_document": document, "issues": uncertain_facts},
                            ensure_ascii=False,
                        )
                    ),
                ]
            )
            decisions = _parse_visual_decisions(str(response.content))
        except Exception as exc:
            adjudication_error = str(exc)

    retry_candidates = unique_text(
        [
            candidate
            for decision in decisions
            for candidate in (decision.get("retry_candidates") or [])
        ],
        limit=24,
    )
    retry_resolutions = []
    if retry_candidates:
        try:
            retry_resolutions = await resolve_tag_candidates(retry_candidates, limit=24)
        except Exception as exc:
            adjudication_error = adjudication_error or str(exc)
    retry_resolutions = [
        {**item, "phase": "adjudication_retry"} for item in retry_resolutions
    ]
    resolutions = [*resolutions, *retry_resolutions]
    resolved_by_input = {
        _normalized(item.get("normalized_input")): item
        for item in resolutions
        if item.get("name")
    }
    resolved_names = {
        _normalized(item.get("name")): _normalized(item.get("name"))
        for item in resolutions
        if item.get("name")
    }
    decisions_by_fact = {
        int(item.get("fact_index")): item
        for item in decisions
        if str(item.get("fact_index", "")).isdigit()
    }
    records = []
    seen_records = set()
    for item in resolutions:
        name = _normalized(item.get("name"))
        if name and name not in seen_records:
            records.append(item)
            seen_records.add(name)
    atomic_terms: list[Dict[str, Any]] = []
    for fact_index, fact in enumerate(atomic_facts):
        source_path = str(fact.get("source_path") or "").strip()
        matched = unique_text(
            [
                resolved_by_input[_normalized(candidate)]["name"]
                for candidate in fact.get("candidates") or []
                if _normalized(candidate) in resolved_by_input
            ],
            limit=8,
        )
        decision = decisions_by_fact.get(fact_index)
        if decision:
            action = str(decision.get("action") or "").strip().lower()
            selected = []
            for value in decision.get("selected_tags") or []:
                key = _normalized(value)
                canonical = resolved_names.get(key) or _normalized(
                    (resolved_by_input.get(key) or {}).get("name")
                )
                if canonical:
                    selected.append(canonical)
            if action == "phrase_only":
                matched = []
            elif selected:
                matched = unique_text(selected, limit=8)
            elif action == "retry":
                matched = unique_text(
                    [
                        resolved_by_input[_normalized(value)]["name"]
                        for value in decision.get("retry_candidates") or []
                        if _normalized(value) in resolved_by_input
                    ],
                    limit=8,
                ) or matched
        if matched:
            for value in matched:
                atomic_terms.append(
                    {
                        "value": value,
                        "kind": "verified_tag",
                        "polarity": "positive",
                        "source_path": source_path,
                        "provenance": "danbooru",
                        "inferred": bool(fact.get("inferred")),
                    }
                )
        fallback = str(fact.get("fallback_phrase") or "").strip()
        if decision and bool(decision.get("preserve_phrase", True)):
            fallback = str(decision.get("preserved_phrase") or fallback).strip()
        elif decision and decision.get("preserve_phrase") is False:
            fallback = ""
        if fallback and _normalized(fallback) not in {_normalized(value) for value in matched}:
            atomic_terms.append(
                {
                    "value": fallback,
                    "kind": "descriptive_phrase",
                    "polarity": "positive",
                    "source_path": source_path,
                    "provenance": "model_fallback",
                    "inferred": bool(fact.get("inferred")),
                }
            )

    relation_terms = [
        {
            "value": str(fact.get("phrase") or "").strip(),
            "kind": "relation_phrase",
            "polarity": "positive",
            "source_path": str(fact.get("source_path") or "").strip(),
            "provenance": "model",
            "inferred": bool(fact.get("inferred")),
        }
        for fact in _facts(parsed.get("relation_facts"))
        if str(fact.get("phrase") or "").strip()
    ]
    if not relation_terms:
        relation_terms = _fallback_relation_terms(document)
    negative_terms = [
        {
            "value": str(fact.get("phrase") or "").strip(),
            "kind": "negative_phrase",
            "polarity": "negative",
            "source_path": str(fact.get("source_path") or "").strip(),
            "provenance": "model",
            "inferred": False,
        }
        for fact in _facts(parsed.get("negative_facts"))
        if str(fact.get("phrase") or "").strip()
    ]
    if not negative_terms:
        negative_terms = [
            {
                "value": value,
                "kind": "negative_phrase",
                "polarity": "negative",
                "source_path": f"/requirements/{key}/{index}",
                "provenance": "document",
                "inferred": False,
            }
            for key in ("negative", "forbidden")
            for index, value in enumerate((document.get("requirements") or {}).get(key) or [])
        ]
    atomic_terms = _merge_incremental_terms(
        previous_ir.get("atomic_terms"), atomic_terms, touched_paths
    )
    relation_terms = _merge_incremental_terms(
        previous_ir.get("relation_terms"), relation_terms, touched_paths
    )
    negative_terms = _merge_incremental_terms(
        previous_ir.get("negative_terms"), negative_terms, touched_paths
    )
    return {
        "atomic_terms": atomic_terms,
        "relation_terms": relation_terms,
        "negative_terms": negative_terms,
        "visual_tag_records": records,
        "visual_tag_resolutions": resolutions,
        "visual_tag_adjudication": {
            "triggered": bool(uncertain_facts),
            "issues": uncertain_facts,
            "decisions": decisions,
            "retry_candidates": retry_candidates,
            "error": adjudication_error,
            "normalization_error": normalization_error,
        },
        "visual_search_terms": candidates,
        "messages": [
            AIMessage(
                content=f"已生成 {len(atomic_terms)} 个原子项和 {len(relation_terms)} 个关系项。",
                name="visual_semantic_resolver",
            )
        ],
    }
# </agent-node>

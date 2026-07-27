"""Business nodes for the prompt_compiler agent."""

from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agents.prompt_generation.prompt_compiler.state import PromptCompilerState

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
    state: PromptCompilerState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Collect current and reusable Prompt IR inputs."""

    # prompt/model/temperature 来自本地 Agent manifest 和 Workflow 节点配置，
    # 由运行时经 Workflow state 注入。
    # 这里可以读取 state["system_prompt"], state["model"], state["temperature"]。
    previous_ir = dict(state.get("previous_resolved_prompt_ir") or {})
    reusable_fields = (
        "identity_terms",
        "atomic_terms",
        "relation_terms",
        "negative_terms",
        "identity_tag_records",
        "identity_tag_resolutions",
        "identity_tag_adjudication",
        "visual_tag_records",
        "visual_tag_resolutions",
        "visual_tag_adjudication",
    )
    context = {
        "previous_resolved_prompt_ir": previous_ir,
        "scene_document": dict(state.get("scene_document") or {}),
        "impact_set": dict(state.get("impact_set") or {}),
        "repair_overlay": dict(state.get("repair_overlay") or {}),
    }
    for field in reusable_fields:
        if field in state:
            context[field] = state[field]
        elif field in previous_ir:
            context[field] = previous_ir[field]
    return {"prepared_context": context}
# </agent-node>


# <agent-node name="collect_terms">
# 中文注意：
# 1. 节点名 "collect_terms" 是 DSL 的稳定标识，不要随手改名。
# 2. 只要 DSL 里还保留这个节点名，刷新骨架时会保留本代码块里的业务逻辑。
# 3. 如果新 DSL 删除了这个节点名，生成器会删除整个代码块，即使里面写过业务代码。
def collect_terms_node(
    state: PromptCompilerState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Collect and normalize semantic terms before compilation."""

    context = dict(state.get("prepared_context") or {})
    previous_ir = context.get("previous_resolved_prompt_ir") or {}
    for field in ("identity_terms", "atomic_terms", "relation_terms", "negative_terms"):
        value = context.get(field) if field in context else previous_ir.get(field)
        context[f"prepared_{field}"] = _entries(value)
    return {"prepared_context": context}
# </agent-node>


# <agent-node name="compile_prompt">
import hashlib
import re


def _key(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().replace("_", " ").split())


def _contains_cjk(value: Any) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", str(value or "")))


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


def _source_paths(item: Dict[str, Any]) -> set[str]:
    return set(re.findall(r"/[^,\s]+", str(item.get("source_path") or "")))


def _paths_overlap(left: set[str], right: set[str]) -> bool:
    return any(
        first == second
        or first.startswith(second.rstrip("/") + "/")
        or second.startswith(first.rstrip("/") + "/")
        for first in left
        for second in right
    )


def _relation_roots(paths: set[str]) -> set[str]:
    return {
        match.group(1)
        for path in paths
        if (match := re.match(r"(/relations/[^/]+)", path))
    }


def _phrase_tokens(value: Any) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", _key(value))
    stopwords = {
        "a", "an", "and", "as", "at", "by", "from", "had", "has", "have",
        "he", "her", "his", "in", "is", "it", "of", "on", "or", "she",
        "the", "they", "to", "with",
    }

    def stem(token: str) -> str:
        if len(token) > 5 and token.endswith("ing"):
            base = token[:-3]
            return base[:-1] if len(base) > 2 and base[-1] == base[-2] else base
        if len(token) > 4 and token.endswith("ed"):
            return token[:-2]
        if len(token) > 4 and token.endswith("es"):
            return token[:-2]
        if len(token) > 3 and token.endswith("s"):
            return token[:-1]
        return token

    return {stem(token) for token in tokens if token not in stopwords}


def _is_verified_term(item: Dict[str, Any]) -> bool:
    return str(item.get("kind") or "").startswith("verified")


def _compact_positive_terms(values: Any) -> list[Dict[str, Any]]:
    """Prefer one complete relation phrase while retaining atomic verified tags."""

    entries = _entries(values)
    relation_indexes: dict[str, int] = {}
    for index, item in enumerate(entries):
        if item.get("kind") != "relation_phrase":
            continue
        for path in _source_paths(item):
            match = re.match(r"(/relations/[^/]+)", path)
            if not match:
                continue
            relation_path = match.group(1)
            previous_index = relation_indexes.get(relation_path)
            if previous_index is None or len(_phrase_tokens(item["value"])) > len(
                _phrase_tokens(entries[previous_index]["value"])
            ):
                relation_indexes[relation_path] = index

    canonical_indexes = set(relation_indexes.values())
    canonical_relations = [entries[index] for index in canonical_indexes]
    compacted = []
    for index, item in enumerate(entries):
        if _is_verified_term(item):
            compacted.append(item)
            continue
        if item.get("kind") == "relation_phrase" and index not in canonical_indexes:
            item_relations = {
                match.group(1)
                for path in _source_paths(item)
                if (match := re.match(r"(/relations/[^/]+)", path))
            }
            if item_relations & set(relation_indexes):
                continue

        tokens = _phrase_tokens(item.get("value"))
        paths = _source_paths(item)
        covered = False
        for relation in canonical_relations:
            if relation is item:
                continue
            relation_tokens = _phrase_tokens(relation.get("value"))
            relation_paths = _source_paths(relation)
            shares_source = _paths_overlap(paths, relation_paths)
            same_relation = bool(
                _relation_roots(paths) & _relation_roots(relation_paths)
            )
            auxiliary_source = any(
                path.startswith(("/requirements/", "/constraint_overlay/"))
                for path in paths
            )
            if not tokens or not relation_tokens or not (shares_source or auxiliary_source):
                continue
            coverage = len(tokens & relation_tokens) / len(tokens)
            shared_tokens = len(tokens & relation_tokens)
            if shared_tokens >= 2 and (
                coverage >= 0.6
                or same_relation
                or (auxiliary_source and len(tokens) <= 4 and coverage >= 0.5)
            ):
                covered = True
                break
        if not covered:
            compacted.append(item)
    return _entries(compacted)


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


def _enrichment_id(item: Dict[str, Any]) -> str:
    identity = "|".join(
        [
            str(item.get("source_path") or ""),
            str(item.get("participant_id") or ""),
            str(item.get("kind") or ""),
            _key(item.get("value")),
        ]
    )
    return "enr_" + hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16]


def compile_prompt_node(
    state: PromptCompilerState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Compile typed resolution outputs into one traceable Prompt IR."""

    from langchain_core.messages import AIMessage

    state = {**state, **dict(state.get("prepared_context") or {})}
    previous_ir = state.get("previous_resolved_prompt_ir") or {}

    def current_or_previous(field: str) -> Any:
        return state.get(field) if field in state else previous_ir.get(field)

    identity_terms = list(state.get("prepared_identity_terms") or _entries(current_or_previous("identity_terms")))
    atomic_terms = list(state.get("prepared_atomic_terms") or _entries(current_or_previous("atomic_terms")))
    relation_terms = list(state.get("prepared_relation_terms") or _entries(current_or_previous("relation_terms")))
    negative_terms = list(state.get("prepared_negative_terms") or _entries(current_or_previous("negative_terms")))
    positive = _entries([*identity_terms, *atomic_terms, *relation_terms])
    negative = _entries(negative_terms)
    impact = state.get("impact_set") or {}

    previous_overlay = dict(previous_ir.get("enrichment_overlay") or {})
    previous_entries = {
        key: dict(value)
        for key, value in (previous_overlay.get("entries") or {}).items()
        if isinstance(value, dict)
    }
    current_entries: Dict[str, Dict[str, Any]] = {}
    for item in positive:
        if not item.get("inferred"):
            continue
        enrichment_id = _enrichment_id(item)
        previous_entry = previous_entries.get(enrichment_id) or {}
        current_entries[enrichment_id] = {
            "id": enrichment_id,
            "value": item["value"],
            "kind": str(item.get("kind") or "descriptive_phrase"),
            "source_path": str(item.get("source_path") or ""),
            "participant_id": str(item.get("participant_id") or ""),
            "status": (
                "rejected"
                if previous_entry.get("status") == "rejected"
                else "active"
            ),
            "created_document_version": int(
                previous_entry.get("created_document_version") or 0
            ),
            **(
                {
                    "rejected_by": previous_entry.get("rejected_by"),
                    "rejected_at_document_version": previous_entry.get(
                        "rejected_at_document_version"
                    ),
                }
                if previous_entry.get("status") == "rejected"
                else {}
            ),
        }
        if not current_entries[enrichment_id]["created_document_version"]:
            current_entries[enrichment_id]["created_document_version"] = int(
                (state.get("scene_document") or {}).get("version") or 0
            )
    for enrichment_id, entry in previous_entries.items():
        if entry.get("status") == "rejected" and enrichment_id not in current_entries:
            current_entries[enrichment_id] = entry
    rejected_enrichment_ids = {
        enrichment_id
        for enrichment_id, entry in current_entries.items()
        if entry.get("status") == "rejected"
    }
    positive = [
        item
        for item in positive
        if not item.get("inferred") or _enrichment_id(item) not in rejected_enrichment_ids
    ]
    constraint_overlay = dict(previous_ir.get("constraint_overlay") or {})
    constraint_entries = {
        key: dict(value)
        for key, value in (constraint_overlay.get("entries") or {}).items()
        if isinstance(value, dict)
    }
    active_constraints = [
        entry
        for entry in constraint_entries.values()
        if entry.get("status") == "active" and str(entry.get("value") or "").strip()
    ]
    positive = _entries(
        [
            *positive,
            *[
                {
                    "value": entry["value"],
                    "kind": "user_constraint",
                    "polarity": "positive",
                    "source_path": f"/constraint_overlay/{entry['id']}",
                    "provenance": "user_feedback",
                    "inferred": False,
                }
                for entry in active_constraints
                if entry.get("polarity") == "positive"
                and not _contains_cjk(entry.get("value"))
            ],
        ]
    )
    negative = _entries(
        [
            *negative,
            *[
                {
                    "value": entry["value"],
                    "kind": "user_constraint",
                    "polarity": "negative",
                    "source_path": f"/constraint_overlay/{entry['id']}",
                    "provenance": "user_feedback",
                    "inferred": False,
                }
                for entry in active_constraints
                if entry.get("polarity") == "negative"
                and not _contains_cjk(entry.get("value"))
            ],
        ]
    )

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
    positive = _compact_positive_terms(positive)
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
        "enrichment_overlay": {
            "version": int(previous_overlay.get("version") or 0),
            "entries": current_entries,
        },
        "constraint_overlay": {
            "version": int(constraint_overlay.get("version") or 0),
            "entries": constraint_entries,
        },
    }
    from app.domains.prompt_generation.models import PromptIR

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


# <agent-node name="validate_prompt_ir">
# 中文注意：
# 1. 节点名 "validate_prompt_ir" 是 DSL 的稳定标识，不要随手改名。
# 2. 只要 DSL 里还保留这个节点名，刷新骨架时会保留本代码块里的业务逻辑。
# 3. 如果新 DSL 删除了这个节点名，生成器会删除整个代码块，即使里面写过业务代码。
def validate_prompt_ir_node(
    state: PromptCompilerState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Validate and normalize the compiled Prompt IR."""

    from app.domains.prompt_generation.models import PromptIR

    prompt_ir = PromptIR.model_validate(state.get("resolved_prompt_ir") or {})
    return {"resolved_prompt_ir": prompt_ir.model_dump(mode="python")}
# </agent-node>

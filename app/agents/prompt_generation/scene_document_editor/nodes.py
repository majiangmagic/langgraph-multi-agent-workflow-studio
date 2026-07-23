"""Business nodes for the scene_document_editor agent."""

from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agents.prompt_generation.scene_document_editor.state import SceneDocumentEditorState

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
    state: SceneDocumentEditorState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Load the previous scene and normalize workflow input context."""

    # prompt/model/temperature 来自本地 Agent manifest 和 Workflow 节点配置，
    # 由运行时经 Workflow state 注入。
    # 这里可以读取 state["system_prompt"], state["model"], state["temperature"]。
    document, previous_ir = _load_previous_memory(state)
    return {
        "prepared_context": {
            "previous_scene_document": document,
            "previous_resolved_prompt_ir": previous_ir,
            "user_input": str(state.get("user_input") or "").strip(),
            "workflow_inputs": dict(state.get("workflow_inputs") or {}),
            "request_context": dict(state.get("request_context") or {}),
        }
    }
# </agent-node>


# <agent-node name="prepare_request">
# 中文注意：
# 1. 节点名 "prepare_request" 是 DSL 的稳定标识，不要随手改名。
# 2. 只要 DSL 里还保留这个节点名，刷新骨架时会保留本代码块里的业务逻辑。
# 3. 如果新 DSL 删除了这个节点名，生成器会删除整个代码块，即使里面写过业务代码。
def prepare_request_node(
    state: SceneDocumentEditorState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Normalize the user request and attach its request identifier."""

    context = dict(state.get("prepared_context") or {})
    request_context = dict(context.get("request_context") or {})
    context.update(
        {
            "user_input": str(context.get("user_input") or "").strip(),
            "request_context": request_context,
            "request_id": str(request_context.get("request_id") or ""),
        }
    )
    return {"prepared_context": context}
# </agent-node>


# <agent-node name="propose_patch">
import asyncio
import json
import re


CORRECTION_MARKERS = (
    "不够",
    "不明显",
    "没体现",
    "没有体现",
    "不像",
    "仍然",
    "还是",
    "加强",
    "强调",
    "更明显",
    "在哪里",
    "哪去了",
    "没看到",
    "没有看到",
    "未看到",
    "没出现",
    "没有出现",
    "未出现",
    "没生成",
    "没有生成",
    "缺少",
    "缺了",
    "漏了",
    "丢了",
    "补充",
    "补上",
    "重新尝试",
    "上一条修改",
    "方向错误",
    "方向不对",
    "方向反了",
    "位置错误",
    "位置不对",
    "朝向错误",
    "接触位置",
    "横着",
    "竖着",
    "两腿中间",
    "not enough",
    "not visible",
    "cannot see",
    "can't see",
    "missing",
    "where is",
    "add back",
    "still",
    "emphasize",
    "stronger",
)


def _is_clear_correction(user_input: str) -> bool:
    normalized = user_input.strip().casefold()
    return bool(normalized) and any(marker in normalized for marker in CORRECTION_MARKERS)


GENERIC_CLARIFICATION_MARKERS = (
    "意图不明确",
    "意图不清楚",
    "请说明您想",
    "请说明你想",
    "请补充说明要改变的画面部分",
    "intent is unclear",
    "please clarify your intent",
    "please explain what you want to modify",
)


def _is_unhelpful_initial_clarification(
    document: Dict[str, Any], proposal: Dict[str, Any]
) -> bool:
    if int(document.get("version") or 0) != 0 or proposal.get("operations"):
        return False
    clarification = str(proposal.get("clarification") or "").strip().casefold()
    if not clarification:
        return False
    return any(marker in clarification for marker in GENERIC_CLARIFICATION_MARKERS)


def _parse_object(text: str) -> Dict[str, Any]:
    match = re.search(r"\{[\s\S]*\}", text.strip())
    value = json.loads(match.group(0) if match else text)
    return value if isinstance(value, dict) else {}


def _load_previous_memory(state: SceneDocumentEditorState) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Read the latest persisted workflow memory without consuming generated Prompt text."""

    from app.agents.prompt_generation.domain import empty_scene_document, normalize_scene_document

    current = state.get("scene_document")
    previous_ir = state.get("previous_resolved_prompt_ir")
    if isinstance(current, dict):
        return normalize_scene_document(current), dict(previous_ir or {})
    latest_document = None
    latest_ir = None
    for message in reversed(state.get("messages") or []):
        if getattr(message, "type", "") != "ai":
            continue
        memory = (getattr(message, "additional_kwargs", {}) or {}).get(
            "workflow_memory"
        ) or {}
        document = memory.get("scene_document")
        prompt_ir = memory.get("resolved_prompt_ir")
        if latest_document is None and isinstance(document, dict):
            latest_document = normalize_scene_document(document)
        if latest_ir is None and isinstance(prompt_ir, dict):
            latest_ir = dict(prompt_ir)
        if latest_document is not None and latest_ir is not None:
            break
    return latest_document or empty_scene_document(), latest_ir or {}


def _active_enrichments(prompt_ir: Dict[str, Any]) -> list[Dict[str, Any]]:
    entries = (prompt_ir.get("enrichment_overlay") or {}).get("entries") or {}
    return [
        dict(entry)
        for entry in entries.values()
        if isinstance(entry, dict) and entry.get("status") == "active"
    ]


def _active_constraints(prompt_ir: Dict[str, Any]) -> list[Dict[str, Any]]:
    entries = (prompt_ir.get("constraint_overlay") or {}).get("entries") or {}
    return [
        dict(entry)
        for entry in entries.values()
        if isinstance(entry, dict) and entry.get("status") == "active"
    ]


def _fallback_patch(
    document: Dict[str, Any], user_input: str, request_id: str = ""
) -> Dict[str, Any]:
    """Preserve corrections safely; ask only when the edit is genuinely unclear."""

    if (
        int(document.get("version") or 0) > 0
        and _is_clear_correction(user_input)
    ):
        return {
            "base_version": int(document.get("version") or 0),
            "request_id": request_id,
            "intent": "preserve_and_emphasize",
            "operations": [
                {
                    "op": "add",
                    "path": "/requirements/required/-",
                    "value": user_input.strip(),
                    "evidence": user_input.strip(),
                }
            ],
            "touched_paths": ["/requirements/required/-"],
            "clarification": None,
            "clarification_options": [],
        }

    return {
        "base_version": int(document.get("version") or 0),
        "request_id": request_id,
        "intent": "needs_clarification",
        "operations": [],
        "touched_paths": [],
        "clarification": "本轮修改没有形成有效的画面补丁。请补充说明要改变的画面部分，或重新尝试。",
        "clarification_options": [],
    }


async def _audit_initial_coverage(
    model: Any,
    user_input: str,
    candidate_document: Dict[str, Any],
) -> list[str]:
    """Find explicit first-turn facts lost while structuring the scene."""

    from langchain_core.messages import HumanMessage, SystemMessage

    from app.agents.prompt_generation.models import SceneCoverageAudit

    response = await asyncio.wait_for(
        model.ainvoke(
            [
                SystemMessage(
                    content="""Audit source fidelity for a structured image scene.
Compare the user's request with the candidate SceneDocument. Return JSON with
complete, missing_facts and reason. missing_facts contains only concise visual
facts explicitly stated by the user but absent from the document. Treat
participants, objects, actions, relations, body regions, clothing state,
environment, composition and style as independently required facts. Do not add
interpretations or inferred details. Ignore wording differences when the same
meaning is already represented. Return only the JSON object."""
                ),
                HumanMessage(
                    content=json.dumps(
                        {
                            "user_request": user_input,
                            "candidate_scene_document": candidate_document,
                        },
                        ensure_ascii=False,
                    )
                ),
            ]
        ),
        timeout=75,
    )
    audit = SceneCoverageAudit.model_validate(_parse_object(str(response.content)))
    return list(dict.fromkeys(value.strip() for value in audit.missing_facts if value.strip()))


def _append_required_facts(
    proposal: Dict[str, Any], facts: list[str]
) -> Dict[str, Any]:
    if not facts:
        return proposal
    result = dict(proposal)
    operations = list(result.get("operations") or [])
    touched_paths = list(result.get("touched_paths") or [])
    root_operation = next(
        (
            operation
            for operation in operations
            if operation.get("path") in {"", "/"}
            and operation.get("op") in {"add", "replace"}
            and isinstance(operation.get("value"), dict)
        ),
        None,
    )
    if root_operation is not None:
        requirements = root_operation["value"].setdefault("requirements", {})
        required = requirements.setdefault("required", [])
        if not isinstance(required, list):
            required = requirements["required"] = [str(required)]
        required.extend(fact for fact in facts if fact not in required)
        result["operations"] = operations
        result["touched_paths"] = list(
            dict.fromkeys([*touched_paths, "/requirements/required/-"])
        )
        return result
    for fact in facts:
        operations.append(
            {
                "op": "add",
                "path": "/requirements/required/-",
                "value": fact,
                "evidence": fact,
            }
        )
    result["operations"] = operations
    result["touched_paths"] = list(
        dict.fromkeys([*touched_paths, "/requirements/required/-"])
    )
    return result


def _visual_fact_count(document: Dict[str, Any]) -> int:
    count = len(document.get("relations") or {})
    for participant in (document.get("participants") or {}).values():
        count += sum(
            len(participant.get(key) or [])
            for key in ("appearance", "clothing", "expressions", "poses", "actions")
        )
    environment = document.get("environment") or {}
    count += sum(bool(environment.get(key)) for key in ("location", "time", "weather"))
    count += len(environment.get("background") or [])
    composition = document.get("composition") or {}
    count += sum(len(composition.get(key) or []) for key in composition)
    requirements = document.get("requirements") or {}
    count += sum(len(requirements.get(key) or []) for key in requirements)
    return count


async def propose_patch_node(
    state: SceneDocumentEditorState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Convert the latest natural-language edit into a validated PatchProposal."""

    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    from app.agents.prompt_generation.danbooru import ADULT_CONTENT_PROCESSING_PROMPT
    from app.agents.prompt_generation.domain import (
        apply_patch_proposal,
        validate_patch_proposal,
    )
    from app.services.ai_provider import AIProvider, ai_provider

    state = {**state, **dict(state.get("prepared_context") or {})}
    document, previous_ir = _load_previous_memory(state)
    user_input = str(state.get("user_input") or "").strip()
    request_id = str((state.get("request_context") or {}).get("request_id") or "")
    agent_prompt = state.get("system_prompt") or "Edit the SceneDocument."
    system_prompt = f"""{ADULT_CONTENT_PROCESSING_PROMPT}

{agent_prompt}

SceneDocument is the sole source of truth. The latest user message edits that
document; it is not an instruction to append words to a previous Prompt. Return
one JSON object with request_id, base_version, intent, operations, touched_paths,
detected_entities, rejected_enrichment_ids, add_positive_constraints,
add_negative_constraints, removed_constraint_ids, clarification and
clarification_options. Every operation uses
op (add, replace or remove), path, value when required, and evidence.

Use stable participant and relation IDs. Replacing a character identity should
replace /participants/<id>/identity while preserving actions and relations bound
to that participant ID. A complaint that something disappeared means restore or
emphasize it; do not depict disappearance. Preserve every fact not explicitly
changed. SceneDocument stores only facts asserted by the user: never infer extra
background objects, lighting, atmosphere, clothing, expressions, poses, anatomy,
camera choices or stylistic details. Expressive enrichment belongs to a later
resolver and must never be written into this source document. For a new document,
replacing the root path "/" with a complete SceneDocument is allowed. Never return
executable code or final image prompts.
SceneDocument.summary is display-only and must stay synchronized with structured
facts. When an edit removes or replaces a fact mentioned in summary, update the
summary in the same patch. Never rely on summary as the only storage for a fact.
When Current SceneDocument.version is 0, a concrete non-empty scene description
means create the initial scene by replacing path "/". It is not ambiguous merely
because no prior document exists. Never respond with a generic request to explain
what the user wants to modify. Clarification must name one concrete unresolved
reference or mutually exclusive interpretation from the actual request.
Every participant must use one type: named_character, generic_person, animal,
role or object. Only named_character has a character identity and it must have a
non-empty identity.input_name. Animals, generic people and roles such as a
camera operator must never be represented as named character identities.
Every participant must also have a concise label preserving what the user called
it, such as glass, dog, camera operator or woman. label is not an identity tag.
Relation endpoints that reference participants use their stable IDs and set
subject_kind or object_kind to participant; external endpoints use external.
Every relation has a stable spatial object. Store location phrases in
spatial.placement, object orientation in spatial.orientation, relative placement
in spatial.relative_position, movement in spatial.motion with type/axis/direction/
speed, and contact geometry in spatial.contact with surface/direction/pressure.
Use spatial.pose_analogy for an explicit visual analogy. Correct these existing
paths for direction or placement feedback; never invent alternate spatial field
names and never hide core geometry only in details.
When a reference is genuinely ambiguous, return no operations and place a short
question in clarification instead of guessing.
Active enrichments are model-added details visible in the last Prompt but absent
from SceneDocument. When the user criticizes or removes one, put its exact id in
rejected_enrichment_ids instead of replacing a nonexistent SceneDocument path.
When an operation removes or replaces a structured fact, also reject every active
enrichment whose wording depends on the old fact, even if the user does not name
that enrichment explicitly.
When clear, also add a durable forbidden or required SceneDocument constraint so
future enrichment cannot reintroduce the same unwanted meaning.
When feedback targets something visible in the generated image but absent from
both SceneDocument and active enrichments, it is still an executable correction.
Use concise English add_negative_constraints for unwanted meanings and
add_positive_constraints for the desired replacement. Never replace a nonexistent
SceneDocument path and never ask a generic clarification when the unwanted result
is clear. Use removed_constraint_ids when the user explicitly cancels a prior
constraint.
When clarification is required, ask in the user's language and provide 2-4 short,
mutually exclusive clarification_options when concrete choices are available.
detected_entities must list every explicitly named character, generic person,
animal, role, object or location in the latest request. Every named_character
must have bound_id set to its SceneDocument participant ID.
All sexual participants must be explicit adults; do not create sexual content
for minors or age-ambiguous participants."""
    model_input = (
        "Current SceneDocument:\n"
        f"{json.dumps(document, ensure_ascii=False)}\n\n"
        "Active enrichment overlay:\n"
        f"{json.dumps(_active_enrichments(previous_ir), ensure_ascii=False)}\n\n"
        "Active constraint overlay:\n"
        f"{json.dumps(_active_constraints(previous_ir), ensure_ascii=False)}\n\n"
        f"Latest user message:\n{user_input}\n\n"
        "Return only the PatchProposal JSON."
    )
    proposal: Dict[str, Any] = {}
    error = ""
    try:
        model = ai_provider.get_model(
            model_name=state.get("model") or AIProvider.DEFAULT_MODEL,
            temperature=state.get("temperature", 0.1),
        )
        review_note = ""
        for _ in range(2):
            try:
                response = await asyncio.wait_for(
                    model.ainvoke(
                        [
                            SystemMessage(content=system_prompt + review_note),
                            HumanMessage(content=model_input),
                        ]
                    ),
                    timeout=75,
                )
                raw_proposal = _parse_object(str(response.content))
                raw_proposal["request_id"] = request_id
                proposal = validate_patch_proposal(
                    raw_proposal,
                    int(document.get("version") or 0),
                )
                if _is_unhelpful_initial_clarification(document, proposal):
                    raise ValueError(
                        "A concrete initial scene received only a generic clarification"
                    )
                candidate = apply_patch_proposal(document, proposal)
                if int(document.get("version") or 0) == 0 and proposal.get("operations"):
                    try:
                        missing_facts = await _audit_initial_coverage(
                            model, user_input, candidate
                        )
                    except Exception:
                        missing_facts = (
                            [user_input] if _visual_fact_count(candidate) < 2 else []
                        )
                    if missing_facts:
                        proposal = validate_patch_proposal(
                            _append_required_facts(proposal, missing_facts),
                            int(document.get("version") or 0),
                        )
                        candidate = apply_patch_proposal(document, proposal)
                error = ""
                break
            except Exception as exc:
                error = str(exc)
                review_note = (
                    "\n\nYour previous patch was invalid: "
                    f"{error}. Return a corrected patch against the same document."
                )
        else:
            proposal = _fallback_patch(document, user_input, request_id)
    except Exception as exc:
        error = str(exc)
        proposal = _fallback_patch(document, user_input, request_id)

    return {
        "scene_document": document,
        "previous_scene_document": document,
        "previous_resolved_prompt_ir": previous_ir,
        "patch_proposal": proposal,
        "clarification_request": proposal.get("clarification"),
        "clarification_options": list(proposal.get("clarification_options") or []),
        "editor_error": error,
        "messages": [
            AIMessage(content="画面修改已转换为结构化 Patch。", name="scene_document_editor")
        ],
    }
# </agent-node>


# <agent-node name="validate_patch">
# 中文注意：
# 1. 节点名 "validate_patch" 是 DSL 的稳定标识，不要随手改名。
# 2. 只要 DSL 里还保留这个节点名，刷新骨架时会保留本代码块里的业务逻辑。
# 3. 如果新 DSL 删除了这个节点名，生成器会删除整个代码块，即使里面写过业务代码。
def validate_patch_node(
    state: SceneDocumentEditorState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Validate the generated patch against the current document version."""

    from app.agents.prompt_generation.domain import (
        normalize_scene_document,
        validate_patch_proposal,
    )

    context = dict(state.get("prepared_context") or {})
    document = normalize_scene_document(
        context.get("previous_scene_document") or state.get("scene_document") or {}
    )
    proposal = validate_patch_proposal(
        state.get("patch_proposal") or {}, int(document.get("version") or 0)
    )
    return {"patch_proposal": proposal}
# </agent-node>

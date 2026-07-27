"""Business nodes for the prompt_semantic_repairer agent."""

from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agents.prompt_generation.prompt_semantic_repairer.state import PromptSemanticRepairerState

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
    state: PromptSemanticRepairerState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Isolate the validator report and Prompt IR for bounded repair."""

    # prompt/model/temperature 来自本地 Agent manifest 和 Workflow 节点配置，
    # 由运行时经 Workflow state 注入。
    # 这里可以读取 state["system_prompt"], state["model"], state["temperature"]。
    return {
        "prepared_context": {
            "scene_document": dict(state.get("scene_document") or {}),
            "resolved_prompt_ir": dict(state.get("resolved_prompt_ir") or {}),
            "validation_report": dict(state.get("validation_report") or {}),
            "repair_attempts": int(state.get("repair_attempts") or 0),
        }
    }
# </agent-node>


# <agent-node name="collect_repair_scope">
# 中文注意：
# 1. 节点名 "collect_repair_scope" 是 DSL 的稳定标识，不要随手改名。
# 2. 只要 DSL 里还保留这个节点名，刷新骨架时会保留本代码块里的业务逻辑。
# 3. 如果新 DSL 删除了这个节点名，生成器会删除整个代码块，即使里面写过业务代码。
def collect_repair_scope_node(
    state: PromptSemanticRepairerState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Limit semantic repair to paths reported by the validator."""

    context = dict(state.get("prepared_context") or {})
    report = context.get("validation_report") or {}
    issue_paths = {
        str(path)
        for issue in report.get("issues") or []
        if isinstance(issue, dict)
        for path in issue.get("affected_paths") or []
        if path
    }
    context["repair_scope"] = {
        "allowed_paths": sorted(set(report.get("missing_paths") or []) | issue_paths),
        "non_english": list(report.get("non_target_language_terms") or []),
    }
    return {"prepared_context": context}
# </agent-node>


# <agent-node name="repair_semantics">
import json
import re


def _parse_overlay(text: str) -> Dict[str, Any]:
    from app.domains.prompt_generation.models import RepairOverlay

    match = re.search(r"\{[\s\S]*\}", text.strip())
    parsed = RepairOverlay.model_validate_json(match.group(0) if match else text)
    return parsed.model_dump(mode="python")


async def repair_semantics_node(
    state: PromptSemanticRepairerState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Repair only validator-reported paths and bind repair to this version."""

    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    from app.domains.prompt_generation.danbooru import ADULT_CONTENT_PROCESSING_PROMPT
    from app.runtime.llm.provider import AIProvider, ai_provider

    state = {**state, **dict(state.get("prepared_context") or {})}
    report = state.get("validation_report") or {}
    prompt_ir = state.get("resolved_prompt_ir") or {}
    repair_scope = state.get("repair_scope") or {}
    allowed_paths = set(repair_scope.get("allowed_paths") or [])
    non_english = set(repair_scope.get("non_english") or [])
    overlay: Dict[str, Any] = {
        "document_version": int((state.get("scene_document") or {}).get("version") or 0),
        "depends_on_paths": sorted(allowed_paths),
        "add_positive": [],
        "add_negative": [],
        "remove_positive": [
            *report.get("conflicting_terms", []),
            *report.get("removed_identity_residue", []),
            *[
                item.get("value")
                for item in prompt_ir.get("positive_terms") or []
                if isinstance(item, dict) and item.get("value") in non_english
            ],
        ],
        "remove_negative": [
            item.get("value")
            for item in prompt_ir.get("compiled_negative_terms") or []
            if isinstance(item, dict) and item.get("value") in non_english
        ],
    }
    if allowed_paths:
        system_prompt = f"""{ADULT_CONTENT_PROCESSING_PROMPT}

{state.get('system_prompt') or ''}

Return one RepairOverlay JSON object with document_version, depends_on_paths,
add_positive, add_negative, remove_positive and remove_negative. Added items must
contain value, source_path and kind. Use concise English image-prompt phrases with
no CJK characters. Cover only allowed_paths. Preserve exact subjects, objects,
spatial relations and identities from SceneDocument. Active constraint_overlay
entries are also authoritative: translate a missing positive constraint into
add_positive and a missing negative constraint into add_negative using its exact
/constraint_overlay/<id> source_path. Do not add new facts."""
        payload = {
            "scene_document": state.get("scene_document") or {},
            "resolved_prompt_ir": prompt_ir,
            "validation_report": report,
            "allowed_paths": sorted(allowed_paths),
        }
        try:
            model = ai_provider.get_model(
                model_name=state.get("model") or AIProvider.DEFAULT_MODEL,
                temperature=state.get("temperature", 0.1),
            )
            response = await model.ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
                ]
            )
            proposed = _parse_overlay(str(response.content))
            overlay["add_positive"] = [
                item
                for item in proposed.get("add_positive") or []
                if item.get("source_path") in allowed_paths
            ]
            overlay["add_negative"] = [
                item
                for item in proposed.get("add_negative") or []
                if item.get("source_path") in allowed_paths
            ]
        except Exception:
            pass
    attempts = int(state.get("repair_attempts") or 0) + 1
    return {
        "repair_overlay": overlay,
        "repair_attempts": attempts,
        "messages": [
            AIMessage(
                content=f"Completed bounded semantic repair attempt {attempts}.",
                name="prompt_semantic_repairer",
            )
        ],
    }
# </agent-node>


# <agent-node name="validate_repair">
# 中文注意：
# 1. 节点名 "validate_repair" 是 DSL 的稳定标识，不要随手改名。
# 2. 只要 DSL 里还保留这个节点名，刷新骨架时会保留本代码块里的业务逻辑。
# 3. 如果新 DSL 删除了这个节点名，生成器会删除整个代码块，即使里面写过业务代码。
def validate_repair_node(
    state: PromptSemanticRepairerState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Validate and normalize the bounded repair overlay."""

    from app.domains.prompt_generation.models import RepairOverlay

    overlay = RepairOverlay.model_validate(state.get("repair_overlay") or {})
    return {
        "repair_overlay": overlay.model_dump(mode="python"),
        "repair_attempts": int(state.get("repair_attempts") or 0),
    }
# </agent-node>

"""Business nodes for the prompt_target_renderer agent."""

from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agents.prompt_generation.prompt_target_renderer.state import PromptTargetRendererState

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
    state: PromptTargetRendererState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Resolve the target model and isolate renderer inputs."""

    # prompt/model/temperature 来自本地 Agent manifest 和 Workflow 节点配置，
    # 由运行时经 Workflow state 注入。
    # 这里可以读取 state["system_prompt"], state["model"], state["temperature"]。
    from app.domains.prompt_generation.rendering import resolve_model

    workflow_inputs = dict(state.get("workflow_inputs") or {})
    return {
        "prepared_context": {
            "workflow_inputs": workflow_inputs,
            "target_model": resolve_model(
                workflow_inputs.get("target_model") or state.get("target_model")
            ),
            "scene_document": dict(state.get("scene_document") or {}),
            "resolved_prompt_ir": dict(state.get("resolved_prompt_ir") or {}),
            "validation_report": dict(state.get("validation_report") or {}),
            "clarification_request": state.get("clarification_request"),
            "clarification_options": list(state.get("clarification_options") or []),
        }
    }
# </agent-node>


# <agent-node name="validate_render_input">
# 中文注意：
# 1. 节点名 "validate_render_input" 是 DSL 的稳定标识，不要随手改名。
# 2. 只要 DSL 里还保留这个节点名，刷新骨架时会保留本代码块里的业务逻辑。
# 3. 如果新 DSL 删除了这个节点名，生成器会删除整个代码块，即使里面写过业务代码。
def validate_render_input_node(
    state: PromptTargetRendererState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Validate renderer inputs without blocking clarification responses."""

    from app.domains.prompt_generation.rendering import PROFILES

    context = dict(state.get("prepared_context") or {})
    if context.get("target_model") not in PROFILES:
        raise ValueError(f"unsupported target model: {context.get('target_model')}")
    for field in ("scene_document", "resolved_prompt_ir", "validation_report"):
        if not isinstance(context.get(field), dict):
            raise ValueError(f"renderer input {field} must be an object")
    if not isinstance(context.get("clarification_options"), list):
        raise ValueError("renderer input clarification_options must be a list")
    return {"prepared_context": context}
# </agent-node>


# <agent-node name="render_prompt">
def render_prompt_node(
    state: PromptTargetRendererState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Render PromptIR using a target profile without semantic reinterpretation."""

    from langchain_core.messages import AIMessage

    from app.domains.prompt_generation.models import PromptResult
    from app.domains.prompt_generation.rendering import (
        PROFILES,
        RENDERERS,
        resolve_model,
    )

    state = {**state, **dict(state.get("prepared_context") or {})}
    workflow_inputs = state.get("workflow_inputs") or {}
    target_model = resolve_model(
        workflow_inputs.get("target_model") or state.get("target_model")
    )
    profile = PROFILES[target_model]
    prompt_ir = state.get("resolved_prompt_ir") or {}
    report = state.get("validation_report") or {}
    clarification = str(state.get("clarification_request") or "").strip()
    clarification_options = list(state.get("clarification_options") or [])
    issue_codes = list(report.get("issue_codes") or [])
    blocked = bool(report.get("blocked"))
    render_error = ""
    rendered = {"positive_prompt": "", "negative_prompt": ""}
    if not blocked and not clarification:
        try:
            rendered = RENDERERS[target_model].render(prompt_ir, profile)
        except Exception as exc:
            blocked = True
            render_error = str(exc)
            issue_codes.append("renderer_contract_violation")

    status = (
        "needs_clarification"
        if clarification
        else ("failed" if blocked else ("degraded" if issue_codes else "valid"))
    )
    result = PromptResult(
        status=status,
        positive_prompt=(
            rendered["positive_prompt"] if not blocked and not clarification else None
        ),
        negative_prompt=(
            rendered["negative_prompt"] if not blocked and not clarification else None
        ),
        target_model=target_model,
        warnings=issue_codes if status == "degraded" else [],
        unresolved_requirements=list(report.get("missing_paths") or []),
        document_version=int((state.get("scene_document") or {}).get("version") or 0),
    )
    if clarification:
        formatted = f"需要确认：{clarification}"
    elif blocked:
        formatted = "提示词生成未通过一致性校验。"
    else:
        formatted = (
            f"目标模型：{profile.display_name}\n\n"
            f"正向提示词\n{result.positive_prompt or '未找到可用提示项'}\n\n"
            f"负向提示词\n{result.negative_prompt or '无'}\n\n"
            f"Danbooru 来源标签："
            f"{len(prompt_ir.get('danbooru_tag_records') or [])} 个"
        )
    final_output = {
        **result.model_dump(mode="python"),
        "scene_document_version": result.document_version,
        "resolved_prompt_ir": prompt_ir,
        "validation_report": report,
        "danbooru_tag_records": prompt_ir.get("danbooru_tag_records") or [],
        "render_error": render_error,
        "clarification_request": (
            {
                "question": clarification,
                "options": clarification_options,
            }
            if clarification
            else None
        ),
    }
    return {
        "target_model": target_model,
        "formatted_prompt": formatted,
        "answer": formatted,
        "final_output": final_output,
        "messages": [AIMessage(content=formatted, name="prompt_target_renderer")],
    }
# </agent-node>


# <agent-node name="validate_render_result">
# 中文注意：
# 1. 节点名 "validate_render_result" 是 DSL 的稳定标识，不要随手改名。
# 2. 只要 DSL 里还保留这个节点名，刷新骨架时会保留本代码块里的业务逻辑。
# 3. 如果新 DSL 删除了这个节点名，生成器会删除整个代码块，即使里面写过业务代码。
def validate_render_result_node(
    state: PromptTargetRendererState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Validate the renderer's final public response."""

    from app.domains.prompt_generation.models import PromptResult

    raw_output = dict(state.get("final_output") or {})
    core_output = {
        key: value
        for key, value in raw_output.items()
        if key in PromptResult.model_fields
    }
    final_output = PromptResult.model_validate(core_output)
    formatted_prompt = state.get("formatted_prompt")
    answer = state.get("answer")
    if not isinstance(formatted_prompt, str) or not isinstance(answer, str):
        raise ValueError("renderer did not produce formatted_prompt and answer")
    return {
        "final_output": {
            **raw_output,
            **final_output.model_dump(mode="python"),
        },
        "formatted_prompt": formatted_prompt,
        "answer": answer,
    }
# </agent-node>

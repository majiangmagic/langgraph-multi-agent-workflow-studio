"""Business nodes for the prompt_target_renderer agent."""

from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agents.prompt_generation.prompt_target_renderer.state import PromptTargetRendererState

# 本文件由 scripts/generate_agent.py 刷新骨架。
# 中文注意：
# - 只在 <agent-node ...> 代码块内部编写业务逻辑。
# - 节点名是 DSL 的稳定标识；节点名不变，刷新时保留对应代码块。
# - 新 DSL 删除某个节点名时，对应代码块会被删除，不会因为里面有人写过代码而保留。

# <agent-node name="render_prompt">
def render_prompt_node(
    state: PromptTargetRendererState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Render PromptIR using a target profile without semantic reinterpretation."""

    from langchain_core.messages import AIMessage

    from app.agents.prompt_generation.models import PromptResult
    from app.agents.prompt_generation.rendering import (
        PROFILES,
        RENDERERS,
        resolve_model,
    )

    workflow_inputs = state.get("workflow_inputs") or {}
    target_model = resolve_model(
        workflow_inputs.get("target_model") or state.get("target_model")
    )
    profile = PROFILES[target_model]
    prompt_ir = state.get("resolved_prompt_ir") or {}
    report = state.get("validation_report") or {}
    clarification = str(state.get("clarification_request") or "").strip()
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
    }
    return {
        "target_model": target_model,
        "formatted_prompt": formatted,
        "answer": formatted,
        "final_output": final_output,
        "messages": [AIMessage(content=formatted, name="prompt_target_renderer")],
    }
# </agent-node>

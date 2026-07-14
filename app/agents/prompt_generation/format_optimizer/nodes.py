"""Business nodes for the prompt_format_optimizer agent."""

from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from app.agents.prompt_generation.format_optimizer.state import PromptFormatOptimizerState

# 本文件由 scripts/generate_agent.py 刷新骨架。
# 中文注意：
# - 只在 <agent-node ...> 代码块内部编写业务逻辑。
# - 节点名是 DSL 的稳定标识；节点名不变，刷新时保留对应代码块。
# - 新 DSL 删除某个节点名时，对应代码块会被删除，不会因为里面有人写过代码而保留。

# <agent-node name="optimize_format">
from typing import Iterable, List


MODEL_ALIASES = {
    "nai": "nai_v4",
    "novelai": "nai_v4",
    "nai4": "nai_v4",
    "nai v4": "nai_v4",
    "nai_v4": "nai_v4",
    "nai3": "nai_v3",
    "nai v3": "nai_v3",
    "nai_v3": "nai_v3",
    "stable diffusion xl": "sdxl",
    "光辉": "illustrious",
    "光輝": "illustrious",
}

MODEL_DEFAULTS = {
    "nai_v4": {
        "positive": ["masterpiece", "best quality", "very aesthetic"],
        "negative": ["lowres", "bad anatomy", "bad hands", "text", "error"],
    },
    "nai_v3": {
        "positive": ["masterpiece", "best quality", "very aesthetic"],
        "negative": ["lowres", "bad anatomy", "bad hands", "text", "error"],
    },
    "sdxl": {
        "positive": ["high quality", "highly detailed"],
        "negative": ["low quality", "blurry", "distorted", "text", "watermark"],
    },
    "illustrious": {
        "positive": ["masterpiece", "best quality", "newest", "very aesthetic"],
        "negative": ["lowres", "worst quality", "bad anatomy", "text", "watermark"],
    },
    "pony": {
        "positive": ["score_9", "score_8_up", "score_7_up"],
        "negative": ["score_4", "score_3", "score_2", "score_1"],
    },
    "flux": {"positive": [], "negative": []},
}


def normalize_model(value: Any) -> str:
    model = str(value or "nai_v4").strip().lower()
    return MODEL_ALIASES.get(model, model if model in MODEL_DEFAULTS else "nai_v4")


def merge_terms(*groups: Iterable[Any]) -> List[str]:
    result: List[str] = []
    seen = set()
    for group in groups:
        for value in group:
            for raw_term in str(value or "").split(","):
                term = raw_term.strip()
                key = term.lower()
                if not term or key in seen:
                    continue
                result.append(term)
                seen.add(key)
    return result


def render_output(model: str, positive: str, negative: str, source_count: int) -> str:
    display_name = {
        "nai_v4": "NAI V4",
        "nai_v3": "NAI V3",
        "sdxl": "SDXL",
        "illustrious": "Illustrious",
        "pony": "Pony",
        "flux": "Flux",
    }.get(model, model.upper())
    return (
        f"目标模型：{display_name}\n\n"
        f"正向提示词\n{positive or '未找到可用标签'}\n\n"
        f"负向提示词\n{negative or '无'}\n\n"
        f"Danbooru 来源标签：{source_count} 个"
    )


def optimize_format_node(
    state: PromptFormatOptimizerState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Apply stable prompt conventions for the selected image model."""

    from langchain_core.messages import AIMessage

    requirements = state.get("requirements_json") or {}
    model = normalize_model(state.get("target_model") or requirements.get("target_model"))
    defaults = MODEL_DEFAULTS[model]
    sections = state.get("prompt_sections") or {}
    verified_tags = merge_terms(
        sections.get("character") or [],
        sections.get("scene") or [],
        sections.get("additional") or [],
    )
    descriptive_phrases = merge_terms(sections.get("descriptive_phrases") or [])
    negative = str(state.get("negative_prompt") or "")
    if model == "nai_v3":
        content_terms = verified_tags
    elif model in {"sdxl", "flux"}:
        content_terms = merge_terms(descriptive_phrases, verified_tags)
    else:
        content_terms = merge_terms(verified_tags, descriptive_phrases)
    positive_terms = merge_terms(defaults["positive"], content_terms)
    negative_terms = merge_terms(defaults["negative"], [negative])

    if model == "flux":
        positive = ". ".join(positive_terms)
    else:
        positive = ", ".join(positive_terms)
    negative_prompt = ", ".join(negative_terms)
    records = state.get("danbooru_tag_records") or []
    formatted = render_output(model, positive, negative_prompt, len(records))
    final_output = {
        "target_model": model,
        "positive_prompt": positive,
        "negative_prompt": negative_prompt,
        "sections": sections,
        "danbooru_tag_records": records,
        "consistency_report": state.get("consistency_report") or {},
        "request_contract": requirements.get("request_contract") or {},
    }
    return {
        "target_model": model,
        "formatted_prompt": formatted,
        "final_output": final_output,
        "messages": [
            AIMessage(content=formatted, name="prompt_format_optimizer")
        ],
    }
# </agent-node>

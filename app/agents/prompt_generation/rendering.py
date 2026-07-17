"""Target-model rendering profiles for PromptIR."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Protocol

from app.agents.prompt_generation.domain import contains_cjk


@dataclass(frozen=True)
class ModelProfile:
    name: str
    display_name: str
    prompt_style: str
    positive_defaults: tuple[str, ...]
    negative_defaults: tuple[str, ...]
    verified_tags_only: bool = False
    phrases_first: bool = False
    sentence_separator: str = ", "


class PromptRenderer(Protocol):
    def render(self, prompt_ir: Dict[str, Any], profile: ModelProfile) -> Dict[str, str]: ...


def _unique(values: Iterable[Any]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        key = text.casefold()
        if text and key not in seen:
            result.append(text)
            seen.add(key)
    return result


class DefaultPromptRenderer:
    """Render terms without reinterpreting their semantics."""

    def render(self, prompt_ir: Dict[str, Any], profile: ModelProfile) -> Dict[str, str]:
        positive_entries = list(prompt_ir.get("positive_terms") or [])
        if profile.verified_tags_only:
            positive_entries = [
                item
                for item in positive_entries
                if str(item.get("kind") or "").startswith("verified")
            ]
        elif profile.phrases_first:
            positive_entries.sort(
                key=lambda item: 0 if "phrase" in str(item.get("kind") or "") else 1
            )
        raw_values = [
            *[item.get("value") for item in positive_entries],
            *[
                item.get("value")
                for item in prompt_ir.get("compiled_negative_terms") or []
            ],
        ]
        if any(contains_cjk(value) for value in raw_values):
            raise ValueError("PromptIR contains non-English renderer terms")
        positive = _unique(
            [*profile.positive_defaults, *[item.get("value") for item in positive_entries]]
        )
        negative = _unique(
            [
                *profile.negative_defaults,
                *[
                    item.get("value")
                    for item in prompt_ir.get("compiled_negative_terms") or []
                ],
            ]
        )
        return {
            "positive_prompt": profile.sentence_separator.join(positive),
            "negative_prompt": ", ".join(negative),
        }


PROFILES = {
    "nai_v4": ModelProfile(
        "nai_v4",
        "NAI V4",
        "hybrid",
        ("masterpiece", "best quality", "very aesthetic"),
        ("lowres", "bad anatomy", "bad hands", "text", "error"),
    ),
    "nai_v3": ModelProfile(
        "nai_v3",
        "NAI V3",
        "danbooru_tags",
        ("masterpiece", "best quality", "very aesthetic"),
        ("lowres", "bad anatomy", "bad hands", "text", "error"),
        verified_tags_only=True,
    ),
    "sdxl": ModelProfile(
        "sdxl",
        "SDXL",
        "hybrid",
        ("high quality", "highly detailed"),
        ("low quality", "blurry", "distorted", "text", "watermark"),
        phrases_first=True,
    ),
    "illustrious": ModelProfile(
        "illustrious",
        "Illustrious",
        "hybrid",
        ("masterpiece", "best quality", "newest", "very aesthetic"),
        ("lowres", "worst quality", "bad anatomy", "text", "watermark"),
    ),
    "pony": ModelProfile(
        "pony",
        "Pony",
        "hybrid",
        ("score_9", "score_8_up", "score_7_up"),
        ("score_4", "score_3", "score_2", "score_1"),
    ),
    "flux": ModelProfile(
        "flux",
        "Flux",
        "natural_language",
        (),
        (),
        phrases_first=True,
        sentence_separator=". ",
    ),
}

MODEL_ALIASES = {
    "nai": "nai_v4",
    "novelai": "nai_v4",
    "nai4": "nai_v4",
    "nai v4": "nai_v4",
    "nai3": "nai_v3",
    "nai v3": "nai_v3",
    "stable diffusion xl": "sdxl",
    "光辉": "illustrious",
}

RENDERERS: Dict[str, PromptRenderer] = {
    name: DefaultPromptRenderer() for name in PROFILES
}


def resolve_model(value: Any) -> str:
    key = str(value or "nai_v4").strip().lower()
    return MODEL_ALIASES.get(key, key if key in PROFILES else "nai_v4")

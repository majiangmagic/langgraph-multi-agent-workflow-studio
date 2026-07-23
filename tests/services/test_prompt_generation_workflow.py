"""Tests for the SceneDocument-based prompt generation workflow."""

from __future__ import annotations

import json
import uuid

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.agents.catalog import resolve_workflow_agent_configs
from app.agents.prompt_generation.domain import (
    apply_patch_proposal,
    collect_required_paths,
    compute_impact_set,
    empty_scene_document,
    normalize_scene_document,
    validate_patch_proposal,
)
from app.agents.prompt_generation.danbooru import select_fuzzy_tag
from app.agents.prompt_generation.character_identity_resolver.nodes import (
    resolve_identities_node,
)
from app.agents.prompt_generation.prompt_compiler.nodes import compile_prompt_node
from app.agents.prompt_generation.prompt_consistency_validator.nodes import (
    validate_prompt_node,
)
from app.agents.prompt_generation.prompt_target_renderer.nodes import render_prompt_node
from app.agents.prompt_generation.scene_document_processor.nodes import (
    apply_patch_node,
    build_agent_contexts_node,
)
from app.agents.prompt_generation.scene_document_editor.nodes import (
    _append_required_facts,
    _fallback_patch,
    _is_unhelpful_initial_clarification,
    _load_previous_memory,
)
from app.agents.prompt_generation.visual_semantic_resolver.nodes import (
    _fallback_relation_terms,
    _merge_incremental_terms,
    _parse_visual_decisions,
    resolve_visual_semantics_node,
)
from app.api.routes.conversation import (
    extract_workflow_interrupt,
    extract_workflow_memory,
    extract_workflow_outcome,
    extract_workflow_result,
)
from app.core.langgraph.workflows.prompt_generation_workflow.graph import (
    WORKFLOW_METADATA,
    create_prompt_generation_workflow_graph,
)
from app.core.langgraph.workflows.prompt_generation_workflow.state import build_initial_state


def sample_document(name: str = "Hatsune Miku", version: int = 1):
    return normalize_scene_document(
        {
            "summary": f"{name} walking on a street",
            "participants": {
                "character_1": {
                    "adult": True,
                    "identity": {"input_name": name},
                    "actions": ["walking"],
                }
            },
            "environment": {"location": "street"},
            "relations": {
                "relation_1": {
                    "subject": "external_hand",
                    "predicate": "pull",
                    "object": "character_1",
                    "instrument": "rope",
                }
            },
        },
        version=version,
    )


def runtime_agents():
    return resolve_workflow_agent_configs(WORKFLOW_METADATA)


def test_patch_replaces_identity_without_rewriting_bound_actions_or_relations():
    document = sample_document()
    proposal = validate_patch_proposal(
        {
            "base_version": 1,
            "intent": "replace_character",
            "operations": [
                {
                    "op": "replace",
                    "path": "/participants/character_1/identity",
                    "value": {"input_name": "Moria Luluka"},
                }
            ],
        },
        1,
    )

    updated = apply_patch_proposal(document, proposal)

    assert updated["version"] == 2
    assert updated["participants"]["character_1"]["identity"]["input_name"] == "Moria Luluka"
    assert updated["participants"]["character_1"]["actions"] == ["walking"]
    assert updated["relations"]["relation_1"]["object"] == "character_1"


def test_relation_fallback_handles_english_relation_without_scope_error():
    document = sample_document()

    terms = _fallback_relation_terms(document)

    assert any(
        item["source_path"] == "/relations/relation_1"
        and "external_hand pull character_1 rope" in item["value"]
        for item in terms
    )


def test_relation_fallback_preserves_structured_spatial_geometry():
    document = sample_document()
    relation = document["relations"]["relation_1"]
    relation["spatial"] = {
        "placement": ["between_legs"],
        "orientation": "vertical",
        "relative_position": "below_body",
        "motion": {
            "type": "rotation",
            "axis": "horizontal_axis",
            "direction": "forward",
            "speed": "fast",
        },
        "contact": {
            "surface": "roller_outer_surface",
            "direction": "upward",
            "pressure": "firm",
        },
        "pose_analogy": "riding_a_wooden_horse",
    }

    phrase = next(
        item["value"]
        for item in _fallback_relation_terms(document)
        if item["source_path"] == "/relations/relation_1"
    )

    assert "between_legs vertical below_body" in phrase
    assert "rotation horizontal_axis forward fast" in phrase
    assert "roller_outer_surface upward firm riding_a_wooden_horse" in phrase


def test_root_patch_binds_detected_named_character_by_exact_identity_name():
    root = empty_scene_document()
    root["participants"] = {
        "character_1": {
            "id": "character_1",
            "type": "named_character",
            "identity": {"input_name": "伊蕾娜"},
        }
    }
    proposal = validate_patch_proposal(
        {
            "base_version": 0,
            "operations": [{"op": "replace", "path": "/", "value": root}],
            "detected_entities": [
                {
                    "source_text": "伊蕾娜",
                    "entity_type": "named_character",
                    "bound_id": "",
                }
            ],
        },
        0,
    )

    assert proposal["detected_entities"][0]["bound_id"] == "character_1"


def test_patch_normalizes_common_entity_field_aliases_and_null_lists():
    root = empty_scene_document()
    root["participants"] = {
        "character_1": {
            "id": "character_1",
            "type": "named_character",
            "identity": {"input_name": "伊蕾娜"},
        }
    }
    proposal = validate_patch_proposal(
        {
            "base_version": 0,
            "operations": [{"op": "replace", "path": "/", "value": root}],
            "clarification_options": None,
            "detected_entities": [
                {"name": "伊蕾娜", "type": "named_character", "bound_id": ""}
            ],
        },
        0,
    )

    assert proposal["clarification_options"] == []
    assert proposal["detected_entities"] == [
        {
            "source_text": "伊蕾娜",
            "entity_type": "named_character",
            "bound_id": "character_1",
        }
    ]


def test_patch_normalizes_detected_entity_kind_alias():
    proposal = validate_patch_proposal(
        {
            "base_version": 0,
            "operations": [],
            "detected_entities": [
                {"source_text": "roller", "kind": "object", "bound_id": "roller"}
            ],
        },
        0,
    )

    assert proposal["detected_entities"][0]["entity_type"] == "object"


def test_patch_preserves_source_language_constraint_overlay_values():
    proposal = validate_patch_proposal(
        {
            "base_version": 0,
            "operations": [],
            "add_negative_constraints": ["不要开心表情"],
        },
        0,
    )

    assert proposal["add_negative_constraints"] == ["不要开心表情"]


def test_patch_rejects_dangling_participant_relations():
    document = sample_document()
    proposal = validate_patch_proposal(
        {
            "base_version": 1,
            "operations": [
                {"op": "remove", "path": "/participants/character_1"}
            ],
        },
        1,
    )

    with pytest.raises(ValueError, match="missing participant"):
        apply_patch_proposal(document, proposal)


def test_relation_normalization_accepts_structured_endpoints_and_action_alias():
    document = normalize_scene_document(
        {
            "participants": {
                "p1": {"type": "generic_person", "label": "woman"},
                "o1": {"type": "object", "label": "glass"},
            },
            "relations": {
                "r1": {
                    "subject": {"id": "p1", "kind": "participant"},
                    "object": {"id": "o1", "kind": "participant"},
                    "action": "pressed_against",
                }
            },
        }
    )

    assert document["relations"]["r1"] == {
        "id": "r1",
        "subject": "p1",
        "predicate": "pressed_against",
        "object": "o1",
        "instrument": "",
        "source": "",
        "body_region": "",
        "details": [],
        "spatial": {
            "placement": [],
            "orientation": "",
            "relative_position": "",
            "motion": {"type": "", "axis": "", "direction": "", "speed": ""},
            "contact": {"surface": "", "direction": "", "pressure": ""},
            "pose_analogy": "",
        },
        "subject_kind": "participant",
        "object_kind": "participant",
    }


def test_relation_normalization_promotes_spatial_aliases_to_schema_v3():
    document = normalize_scene_document(
        {
            "relations": {
                "r1": {
                    "subject": "roller",
                    "predicate": "rub",
                    "object": "character",
                    "placement": "between_legs",
                    "orientation": "vertical",
                    "relative_position": "below_body",
                    "motion_type": "rotation",
                    "motion_axis": "horizontal_axis",
                    "motion_direction": "forward",
                    "contact_surface": "roller_outer_surface",
                    "contact_direction": "upward",
                    "pose_analogy": "riding_a_wooden_horse",
                }
            }
        }
    )

    relation = document["relations"]["r1"]
    assert document["schema_version"] == 3
    assert relation["spatial"]["placement"] == ["between_legs"]
    assert relation["spatial"]["orientation"] == "vertical"
    assert relation["spatial"]["motion"] == {
        "type": "rotation",
        "axis": "horizontal_axis",
        "direction": "forward",
        "speed": "",
    }
    assert relation["spatial"]["contact"]["direction"] == "upward"


def test_identity_only_change_does_not_invalidate_visual_resolution():
    previous = sample_document()
    current = sample_document("Moria Luluka", version=2)

    impact = compute_impact_set(previous, current)

    assert impact["identity_changed"] is True
    assert impact["visual_changed"] is False
    assert "Hatsune Miku" in impact["removed_identity_terms"]


def test_processor_splits_identity_and_visual_agent_contexts():
    document = sample_document()

    result = build_agent_contexts_node({"scene_document": document})

    identity_participant = result["identity_context"]["participants"]["character_1"]
    visual_participant = result["visual_context"]["participants"]["character_1"]
    assert identity_participant["identity"]["input_name"] == "Hatsune Miku"
    assert "actions" not in identity_participant
    assert "identity" not in visual_participant
    assert visual_participant["actions"] == ["walking"]
    assert result["visual_context"]["environment"]["location"] == "street"
    assert "environment" not in result["identity_context"]


def test_adding_participant_does_not_mark_preserved_resolved_identities_removed():
    previous = sample_document()
    result = apply_patch_node(
        {
            "previous_scene_document": previous,
            "previous_resolved_prompt_ir": {
                "identity_terms": [
                    {
                        "value": "Hatsune Miku",
                        "participant_id": "character_1",
                    }
                ]
            },
            "patch_proposal": {
                "base_version": 1,
                "intent": "add_cameraman",
                "operations": [
                    {
                        "op": "add",
                        "path": "/participants/cameraman",
                        "value": {
                            "id": "cameraman",
                            "type": "human",
                            "adult": True,
                            "identity": {"input_name": "cameraman"},
                        },
                    }
                ],
            },
        }
    )

    assert result["impact_set"]["identity_changed"] is True
    assert result["impact_set"]["removed_identity_terms"] == []


def test_replacing_participant_identity_marks_previous_resolved_name_removed():
    previous = sample_document()
    result = apply_patch_node(
        {
            "previous_scene_document": previous,
            "previous_resolved_prompt_ir": {
                "identity_terms": [
                    {
                        "value": "Hatsune Miku",
                        "participant_id": "character_1",
                    }
                ]
            },
            "patch_proposal": {
                "base_version": 1,
                "intent": "replace_character",
                "operations": [
                    {
                        "op": "replace",
                        "path": "/participants/character_1/identity",
                        "value": {"input_name": "Moria Luluka"},
                    }
                ],
            },
        }
    )

    assert "Hatsune Miku" in result["impact_set"]["removed_identity_terms"]


def test_document_normalization_removes_identity_duplicates_from_requirements():
    document = normalize_scene_document(
        {
            "participants": {
                "character_1": {"identity": {"input_name": "Hatsune Miku"}}
            },
            "requirements": {
                "positive": ["Hatsune Miku", "standing"],
                "required": ["Hatsune Miku", "full body"],
            },
        }
    )

    assert document["requirements"]["positive"] == ["standing"]
    assert document["requirements"]["required"] == ["full body"]


def test_compiler_removes_old_identity_and_applies_repair_overlay():
    result = compile_prompt_node(
        {
            "scene_document": sample_document("Moria Luluka", version=2),
            "impact_set": {"removed_identity_terms": ["hatsune_miku"]},
            "identity_terms": [
                {"value": "moria_luluka", "source_path": "/participants/character_1/identity"},
                {"value": "hatsune_miku", "source_path": "/participants/character_1/identity"},
            ],
            "atomic_terms": [{"value": "street", "source_path": "/environment/location"}],
            "relation_terms": [],
            "negative_terms": [{"value": "text", "source_path": "/requirements/negative/0"}],
            "identity_tag_records": [],
            "visual_tag_records": [],
            "repair_overlay": {
                "remove_positive": ["street"],
                "add_positive": [
                    {"value": "city street", "source_path": "/environment/location"}
                ],
            },
        }
    )
    values = [item["value"] for item in result["resolved_prompt_ir"]["positive_terms"]]

    assert "moria_luluka" in values
    assert "hatsune_miku" not in values
    assert "street" not in values
    assert "city street" in values


def test_validator_reports_missing_paths_and_polarity_conflicts():
    document = sample_document()
    result = validate_prompt_node(
        {
            "scene_document": document,
            "impact_set": {"removed_identity_terms": []},
            "resolved_prompt_ir": {
                "positive_terms": [{"value": "street", "source_path": "/environment/location"}],
                "compiled_negative_terms": [{"value": "street", "source_path": "/requirements/negative/0"}],
                "covered_paths": ["/environment/location"],
            },
        }
    )

    assert result["needs_repair"] is True
    assert "positive_negative_conflict" in result["validation_report"]["issue_codes"]
    assert set(result["validation_report"]["missing_paths"]) == (
        set(collect_required_paths(document)) - {"/environment/location"}
    )


def test_validator_requires_every_active_constraint_to_be_compiled():
    document = normalize_scene_document({}, version=2)
    constraint_path = "/constraint_overlay/con_no_closeup"
    result = validate_prompt_node(
        {
            "scene_document": document,
            "impact_set": {"removed_identity_terms": []},
            "resolved_prompt_ir": {
                "positive_terms": [],
                "compiled_negative_terms": [],
                "covered_paths": [],
                "constraint_overlay": {
                    "entries": {
                        "con_no_closeup": {
                            "id": "con_no_closeup",
                            "value": "避免特写",
                            "polarity": "negative",
                            "status": "active",
                        }
                    }
                },
            },
        }
    )

    assert result["needs_repair"] is True
    assert constraint_path in result["validation_report"]["missing_paths"]


def test_renderer_keeps_phrases_for_nai_v4_but_not_nai_v3():
    state = {
        "scene_document": sample_document(),
        "resolved_prompt_ir": {
            "positive_terms": [
                {"value": "hatsune_miku", "kind": "verified_identity_tag"},
                {"value": "a hand pulling her by a rope", "kind": "relation_phrase"},
            ],
            "compiled_negative_terms": [],
            "danbooru_tag_records": [{"name": "hatsune_miku"}],
        },
        "validation_report": {"valid": True},
    }
    v4 = render_prompt_node({**state, "workflow_inputs": {"target_model": "nai_v4"}})
    v3 = render_prompt_node({**state, "workflow_inputs": {"target_model": "nai_v3"}})

    assert "a hand pulling her by a rope" in v4["final_output"]["positive_prompt"]
    assert "a hand pulling her by a rope" not in v3["final_output"]["positive_prompt"]
    assert "hatsune_miku" in v3["final_output"]["positive_prompt"]


def test_compiler_compacts_relation_phrases_but_keeps_verified_tags():
    result = compile_prompt_node(
        {
            "scene_document": sample_document(version=2),
            "identity_terms": [],
            "atomic_terms": [
                {
                    "value": "between_legs",
                    "kind": "verified_tag",
                    "source_path": "/relations/relation_1/spatial",
                },
                {
                    "value": "The roller is placed between her legs.",
                    "kind": "descriptive_phrase",
                    "source_path": "/relations/relation_1/spatial",
                },
                {
                    "value": "The roller is oriented vertically.",
                    "kind": "descriptive_phrase",
                    "source_path": "/relations/relation_1/spatial",
                },
                {
                    "value": "wooden_horse",
                    "kind": "verified_tag",
                    "source_path": "/relations/relation_1/spatial",
                },
            ],
            "relation_terms": [
                {
                    "value": "A roller rubs against the character.",
                    "kind": "relation_phrase",
                    "source_path": "/relations/relation_1",
                },
                {
                    "value": (
                        "A bumpy roller is positioned vertically between her legs, "
                        "rubbing her as she rides it like a wooden horse."
                    ),
                    "kind": "relation_phrase",
                    "source_path": "/relations/relation_1/spatial",
                },
                {
                    "value": (
                        "The roller is positioned vertically between the legs, "
                        "rubbing her like riding a wooden horse."
                    ),
                    "kind": "user_constraint",
                    "source_path": "/constraint_overlay/c1",
                },
            ],
            "negative_terms": [],
            "impact_set": {"removed_identity_terms": []},
        }
    )
    values = [item["value"] for item in result["resolved_prompt_ir"]["positive_terms"]]

    assert "between_legs" in values
    assert "wooden_horse" in values
    assert "A roller rubs against the character." not in values
    assert "The roller is placed between her legs." not in values
    assert "The roller is oriented vertically." not in values
    assert sum("wooden horse" in value.casefold() for value in values) == 1


def test_visual_decision_parser_accepts_phrase_in_boolean_field():
    decisions = _parse_visual_decisions(
        json.dumps(
            {
                "decisions": [
                    {
                        "fact_index": 0,
                        "action": "phrase_only",
                        "preserve_phrase": "wide shot with the full setup visible",
                    }
                ]
            }
        )
    )

    assert decisions[0]["preserve_phrase"] is True
    assert decisions[0]["preserved_phrase"] == "wide shot with the full setup visible"


def test_incremental_merge_drops_non_authoritative_summary_terms():
    merged = _merge_incremental_terms(
        [
            {
                "value": "The character is sticking out her tongue.",
                "source_path": "/summary",
            },
            {"value": "daytime street", "source_path": "/environment/location"},
        ],
        [{"value": "crawling", "source_path": "/participants/p1/actions/0"}],
        ["/participants/p1/actions/0"],
    )

    assert [item["value"] for item in merged] == ["daytime street", "crawling"]


def test_fuzzy_tag_correction_accepts_typo_but_rejects_ambiguous_candidates():
    corrected = select_fuzzy_tag(
        "streaming_teers",
        [
            {"name": "streaming_tears", "category": 0, "post_count": 100},
            {"name": "streaming_hair", "category": 0, "post_count": 1000},
        ],
    )
    ambiguous = select_fuzzy_tag(
        "catz",
        [
            {"name": "cats", "category": 0, "post_count": 100},
            {"name": "cat", "category": 0, "post_count": 1000},
        ],
    )

    assert corrected and corrected["name"] == "streaming_tears"
    assert ambiguous is None


@pytest.mark.asyncio
async def test_visual_resolver_keeps_residual_phrase_when_tag_covers_only_part(monkeypatch):
    class CameraModel:
        async def ainvoke(self, messages):
            return AIMessage(
                content=json.dumps(
                    {
                        "atomic_facts": [
                            {
                                "source_path": "/composition/camera/0",
                                "candidates": ["full_body"],
                                "fallback_phrase": "wide shot, full body visible",
                            }
                        ],
                        "relation_facts": [],
                        "negative_facts": [],
                    }
                )
            )

    async def resolve_candidates(terms, limit=24):
        return [
            {
                "original": "full_body",
                "normalized_input": "full_body",
                "name": "full_body",
                "category": 0,
                "post_count": 100,
                "status": "verified",
                "confidence": 1.0,
            }
        ]

    monkeypatch.setattr(
        "app.services.ai_provider.ai_provider.get_model",
        lambda **kwargs: CameraModel(),
    )
    monkeypatch.setattr(
        "app.agents.prompt_generation.danbooru.resolve_tag_candidates",
        resolve_candidates,
    )
    result = await resolve_visual_semantics_node(
        {
            "visual_context": normalize_scene_document(
                {"composition": {"camera": ["wide shot, full body visible"]}},
                version=2,
            ),
            "impact_set": {"visual_changed": True},
            "workflow_inputs": {"prompt_strategy": "faithful"},
            "messages": [],
        }
    )
    values = [item["value"] for item in result["atomic_terms"]]

    assert values == ["full_body", "wide shot, full body visible"]


@pytest.mark.asyncio
async def test_visual_adjudicator_retries_typo_and_keeps_pseudo_tag_as_phrase(monkeypatch):
    class AdjudicationModel:
        def __init__(self):
            self.calls = 0

        async def ainvoke(self, messages):
            self.calls += 1
            if self.calls == 1:
                return AIMessage(
                    content=json.dumps(
                        {
                            "atomic_facts": [
                                {
                                    "source_path": "/requirements/required/0",
                                    "candidates": ["strming_ters_xx"],
                                    "fallback_phrase": "tears streaming down her face",
                                },
                                {
                                    "source_path": "/composition/camera/0",
                                    "candidates": ["full_suspension_context"],
                                    "fallback_phrase": "the entire suspension setup visible",
                                },
                            ],
                            "relation_facts": [],
                            "negative_facts": [],
                        }
                    )
                )
            return AIMessage(
                content=json.dumps(
                    {
                        "decisions": [
                            {
                                "fact_index": 0,
                                "action": "retry",
                                "selected_tags": ["streaming_tears"],
                                "retry_candidates": ["streaming_tears"],
                                "preserve_phrase": False,
                            },
                            {
                                "fact_index": 1,
                                "action": "phrase_only",
                                "selected_tags": [],
                                "retry_candidates": [],
                                "preserve_phrase": True,
                                "preserved_phrase": "the entire suspension setup visible",
                            },
                        ]
                    }
                )
            )

    model = AdjudicationModel()

    async def resolve_candidates(terms, limit=24):
        return [
            {
                "original": term,
                "normalized_input": term,
                "name": "streaming_tears" if term == "streaming_tears" else "",
                "category": 0,
                "post_count": 100 if term == "streaming_tears" else 0,
                "status": "verified" if term == "streaming_tears" else "unverified",
                "confidence": 1.0 if term == "streaming_tears" else 0.0,
            }
            for term in terms
        ]

    monkeypatch.setattr(
        "app.services.ai_provider.ai_provider.get_model",
        lambda **kwargs: model,
    )
    monkeypatch.setattr(
        "app.agents.prompt_generation.danbooru.resolve_tag_candidates",
        resolve_candidates,
    )
    result = await resolve_visual_semantics_node(
        {
            "visual_context": normalize_scene_document(
                {
                    "composition": {"camera": ["entire suspension setup"]},
                    "requirements": {"required": ["tears streaming down her face"]},
                },
                version=2,
            ),
            "impact_set": {"visual_changed": True},
            "workflow_inputs": {"prompt_strategy": "faithful"},
            "messages": [],
        }
    )
    values = [item["value"] for item in result["atomic_terms"]]

    assert values == ["streaming_tears", "the entire suspension setup visible"]
    assert model.calls == 2
    assert result["visual_tag_adjudication"]["retry_candidates"] == ["streaming_tears"]
    assert any(
        item.get("phase") == "adjudication_retry"
        for item in result["visual_tag_resolutions"]
    )


@pytest.mark.asyncio
async def test_identity_adjudicator_retries_unverified_character_tag(monkeypatch):
    class IdentityModel:
        def __init__(self):
            self.calls = 0

        async def ainvoke(self, messages):
            self.calls += 1
            if self.calls == 1:
                return AIMessage(
                    content=json.dumps(
                        {
                            "identities": [
                                {
                                    "participant_id": "character_1",
                                    "input_name": "Hatsune Miku",
                                    "canonical_name": "Hatsune Miku",
                                    "series": "Vocaloid",
                                    "danbooru_tag_candidates": ["hatsne_miku"],
                                }
                            ]
                        }
                    )
                )
            return AIMessage(
                content=json.dumps(
                    {
                        "decisions": [
                            {
                                "participant_id": "character_1",
                                "action": "retry",
                                "selected_tag": "hatsune_miku",
                                "retry_candidates": ["hatsune_miku"],
                                "canonical_name": "Hatsune Miku",
                            }
                        ]
                    }
                )
            )

    model = IdentityModel()

    async def resolve_candidates(terms, limit=24):
        return [
            {
                "original": term,
                "normalized_input": term.lower().replace(" ", "_"),
                "name": "hatsune_miku" if term == "hatsune_miku" else "",
                "category": 4 if term == "hatsune_miku" else 0,
                "post_count": 100 if term == "hatsune_miku" else 0,
                "status": "verified" if term == "hatsune_miku" else "unverified",
                "confidence": 1.0 if term == "hatsune_miku" else 0.0,
            }
            for term in terms
        ]

    monkeypatch.setattr(
        "app.services.ai_provider.ai_provider.get_model",
        lambda **kwargs: model,
    )
    monkeypatch.setattr(
        "app.agents.prompt_generation.danbooru.resolve_tag_candidates",
        resolve_candidates,
    )
    result = await resolve_identities_node(
        {
            "identity_context": sample_document(),
            "impact_set": {"identity_changed": True},
            "workflow_inputs": {},
            "messages": [],
        }
    )

    assert result["identity_terms"][0]["value"] == "hatsune_miku"
    assert result["identity_terms"][0]["kind"] == "verified_identity_tag"
    assert model.calls == 2
    assert result["identity_tag_adjudication"]["triggered"] is True


class WorkflowModel(BaseChatModel):
    """Deterministic structured responses for two workflow turns."""

    bound_tools: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "prompt-workflow-test"

    def bind_tools(self, tools, **kwargs):
        self.bound_tools = [tool.name for tool in tools]
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(
            generations=[ChatGeneration(message=self._response(messages))]
        )

    def _response(self, messages):
        system = str(messages[0].content)
        payload = str(messages[-1].content)
        if "You supervise an explicit LangGraph workflow" in system:
            marker = "Current control state:\n"
            control = json.loads(system.rsplit(marker, 1)[1].strip())
            runs = control.get("worker_runs") or {}
            order = [
                "scene_document_editor",
                "scene_document_processor",
                "identity_impact_router",
                "character_identity_resolver",
                "visual_impact_router",
                "visual_semantic_resolver",
                "prompt_compiler",
                "consistency_validator",
                "target_renderer",
            ]
            target = next((name for name in order if not runs.get(name)), None)
            if target:
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": f"route_to_{target}",
                            "args": {},
                            "id": f"delegate-{target}",
                        }
                    ],
                )
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "finish_workflow",
                        "args": {},
                        "id": "finish-workflow",
                    }
                ],
            )
        if "base_version" in system and "SceneDocument" in system:
            if "replace character" in payload:
                content = {
                    "base_version": 1,
                    "intent": "replace_character",
                    "operations": [
                        {
                            "op": "replace",
                            "path": "/participants/character_1/identity",
                            "value": {"input_name": "Moria Luluka"},
                            "evidence": "replace character",
                        }
                    ],
                }
            else:
                document = sample_document(version=0)
                document.pop("version", None)
                document["relations"] = {}
                content = {
                    "base_version": 0,
                    "intent": "create",
                    "operations": [{"op": "replace", "path": "/", "value": document}],
                }
            return AIMessage(content=json.dumps(content))
        if "danbooru_tag_candidates" in system:
            name = "Moria Luluka" if "Moria Luluka" in payload else "Hatsune Miku"
            tag = "moria_luluka" if name == "Moria Luluka" else "hatsune_miku"
            return AIMessage(
                content=json.dumps(
                    {
                        "identities": [
                            {
                                "participant_id": "character_1",
                                "input_name": name,
                                "canonical_name": name,
                                "series": "test",
                                "danbooru_tag_candidates": [tag],
                            }
                        ]
                    }
                )
            )
        if "atomic_facts" in system:
            return AIMessage(
                content=json.dumps(
                    {
                        "atomic_facts": [
                            {
                                "source_path": "/participants/character_1/actions/0",
                                "candidates": ["walking"],
                                "fallback_phrase": "walking",
                            },
                            {
                                "source_path": "/environment/location",
                                "candidates": ["street"],
                                "fallback_phrase": "street",
                            },
                        ],
                        "relation_facts": [],
                        "negative_facts": [],
                    }
                )
            )
        return AIMessage(content="{}")


@pytest.mark.asyncio
async def test_workflow_replaces_character_across_turns_without_reparsing_visuals(monkeypatch):
    monkeypatch.setattr(
        "app.services.ai_provider.ai_provider.get_model",
        lambda **kwargs: WorkflowModel(),
    )

    async def resolve_candidates(terms, limit=24):
        return [
            {
                "name": term,
                "original": term,
                "normalized_input": term,
                "status": "verified",
                "confidence": 1.0,
                "category": 4 if term in {"hatsune_miku", "moria_luluka"} else 0,
                "post_count": 100,
            }
            for term in terms
        ]

    monkeypatch.setattr(
        "app.agents.prompt_generation.danbooru.resolve_tag_candidates",
        resolve_candidates,
    )
    agents = runtime_agents()
    workflow = create_prompt_generation_workflow_graph("crew-1", agents)
    thread_id = str(uuid.uuid4())
    first = await workflow.ainvoke(
        build_initial_state(
            "crew-1",
            agents,
            conversation_id=thread_id,
            user_input="create character",
            workflow_inputs={"target_model": "nai_v4", "prompt_strategy": "faithful"},
        ),
        config={"configurable": {"thread_id": thread_id}},
    )
    memory = extract_workflow_memory(first)
    first_answer = first["nodes"]["target_renderer"]["answer"]
    assert "hatsune_miku" in first_answer

    second = await workflow.ainvoke(
        build_initial_state(
            "crew-1",
            agents,
            conversation_id=thread_id,
            user_input="replace character",
            messages=[
                AIMessage(
                    content=first_answer,
                    additional_kwargs={"workflow_memory": memory},
                )
            ],
            workflow_inputs={"target_model": "nai_v4", "prompt_strategy": "faithful"},
        ),
        config={"configurable": {"thread_id": thread_id}},
    )
    answer = second["nodes"]["target_renderer"]["answer"]
    impact = second["nodes"]["scene_document_processor"]["impact_set"]

    assert "moria_luluka" in answer
    assert "hatsune_miku" not in answer
    assert "walking" in answer and "street" in answer
    assert impact["identity_changed"] is True
    assert impact["visual_changed"] is False


def test_extract_workflow_memory_prefers_scene_document_contract():
    document = sample_document(version=3)
    memory = extract_workflow_memory(
        {
            "nodes": {
                "processor": {"scene_document": document},
                "compiler": {"resolved_prompt_ir": {"document_version": 3}},
            }
        }
    )

    assert memory["scene_document"]["version"] == 3
    assert memory["resolved_prompt_ir"]["document_version"] == 3


def test_extract_workflow_outcome_exposes_resumable_interrupt():
    class Paused:
        id = "interrupt-1"
        value = {
            "kind": "workflow.clarification",
            "question": "镜头从哪个方向拍摄？",
            "options": ["正面", "侧面"],
            "context": "构图信息不足",
        }

    state = {"nodes": {}, "__interrupt__": [Paused()]}
    interrupted = extract_workflow_interrupt(state)
    content, memory, result = extract_workflow_outcome(state)

    assert interrupted["id"] == "interrupt-1"
    assert content == "需要确认：镜头从哪个方向拍摄？"
    assert memory == {}
    assert result["resumable"] is True
    assert result["clarification_request"]["options"] == ["正面", "侧面"]


def test_extract_workflow_memory_preserves_previous_ir_on_clarification_path():
    document = sample_document(version=4)
    memory = extract_workflow_memory(
        {
            "nodes": {
                "editor": {
                    "scene_document": document,
                    "previous_resolved_prompt_ir": {
                        "document_version": 4,
                        "identity_terms": [{"value": "elaina_tag"}],
                    },
                },
                "renderer": {"scene_document": document},
            }
        }
    )

    assert memory["resolved_prompt_ir"]["identity_terms"] == [
        {"value": "elaina_tag"}
    ]


def test_editor_loads_document_and_ir_from_different_recent_messages():
    document = sample_document(version=4)
    loaded_document, loaded_ir = _load_previous_memory(
        {
            "messages": [
                AIMessage(
                    content="valid prompt",
                    additional_kwargs={
                        "workflow_memory": {
                            "scene_document": sample_document(version=3),
                            "resolved_prompt_ir": {
                                "document_version": 3,
                                "identity_terms": [{"value": "elaina_tag"}],
                            },
                        }
                    },
                ),
                AIMessage(
                    content="clarification",
                    additional_kwargs={
                        "workflow_memory": {"scene_document": document}
                    },
                ),
            ]
        }
    )

    assert loaded_document["version"] == 4
    assert loaded_ir["document_version"] == 3


def test_enrichment_overlay_rejection_filters_inferred_prompt_term():
    document = sample_document(version=2)
    first = compile_prompt_node(
        {
            "identity_context": document,
            "previous_resolved_prompt_ir": {},
            "impact_set": {},
            "identity_terms": [],
            "atomic_terms": [
                {
                    "value": "happy expression",
                    "kind": "descriptive_phrase",
                    "source_path": "/composition/style/0",
                    "inferred": True,
                }
            ],
            "relation_terms": [],
            "negative_terms": [],
        }
    )["resolved_prompt_ir"]
    enrichment_id = next(iter(first["enrichment_overlay"]["entries"]))
    first["enrichment_overlay"]["entries"][enrichment_id]["status"] = "rejected"

    second = compile_prompt_node(
        {
            "identity_context": document,
            "previous_resolved_prompt_ir": first,
            "impact_set": {"rejected_enrichment_ids": [enrichment_id]},
        }
    )["resolved_prompt_ir"]

    assert second["positive_terms"] == []
    assert second["enrichment_overlay"]["entries"][enrichment_id]["status"] == "rejected"


def test_processor_marks_enrichment_as_rejected_without_scene_replacement():
    document = sample_document(version=2)
    previous_ir = {
        "document_version": 2,
        "identity_terms": [],
        "enrichment_overlay": {
            "version": 1,
            "entries": {
                "enr_happy": {
                    "id": "enr_happy",
                    "value": "happy expression",
                    "status": "active",
                }
            },
        },
    }
    result = apply_patch_node(
        {
            "previous_scene_document": document,
            "previous_resolved_prompt_ir": previous_ir,
            "patch_proposal": {
                "base_version": 2,
                "operations": [],
                "rejected_enrichment_ids": ["enr_happy"],
            },
        }
    )

    entry = result["previous_resolved_prompt_ir"]["enrichment_overlay"]["entries"][
        "enr_happy"
    ]
    assert entry["status"] == "rejected"
    assert result["impact_set"]["visual_changed"] is True


def test_user_feedback_constraints_are_persisted_and_compiled():
    document = sample_document(version=2)
    processed = apply_patch_node(
        {
            "previous_scene_document": document,
            "previous_resolved_prompt_ir": {
                "document_version": 2,
                "identity_terms": [],
                "atomic_terms": [],
                "relation_terms": [],
                "negative_terms": [],
            },
            "patch_proposal": {
                "base_version": 2,
                "operations": [],
                "add_positive_constraints": ["tense distressed expression"],
                "add_negative_constraints": ["happy expression", "smile"],
            },
        }
    )
    compiled = compile_prompt_node(
        {
            "scene_document": document,
            "previous_resolved_prompt_ir": processed["previous_resolved_prompt_ir"],
            "impact_set": processed["impact_set"],
        }
    )["resolved_prompt_ir"]

    assert "tense distressed expression" in [
        item["value"] for item in compiled["positive_terms"]
    ]
    assert {"happy expression", "smile"}.issubset(
        {item["value"] for item in compiled["compiled_negative_terms"]}
    )
    assert compiled["constraint_overlay"]["version"] == 1


def test_clear_result_complaint_falls_back_to_safe_emphasis_patch():
    proposal = _fallback_patch(
        sample_document(version=2),
        "玻璃不够明显，像压在空气上",
        "request-1",
    )

    assert proposal["intent"] == "preserve_and_emphasize"
    assert proposal["clarification"] is None
    assert proposal["operations"] == [
        {
            "op": "add",
            "path": "/requirements/required/-",
            "value": "玻璃不够明显，像压在空气上",
            "evidence": "玻璃不够明显，像压在空气上",
        }
    ]


@pytest.mark.parametrize(
    "message",
    [
        "被推在玻璃上的行为在哪里",
        "生成结果没有看到玻璃上的挤压行为，补充这一段",
        "这个核心动作漏了，请补上",
        "请重新尝试应用我上一条修改要求，其他画面内容保持不变",
        "方向错误了，滚轮应该竖着放在两腿中间",
    ],
)
def test_natural_missing_feedback_is_an_executable_correction(message):
    proposal = _fallback_patch(sample_document(version=2), message, "request-2")

    assert proposal["intent"] == "preserve_and_emphasize"
    assert proposal["clarification"] is None
    assert proposal["operations"][0]["value"] == message


def test_initial_coverage_facts_are_merged_into_root_document_patch():
    proposal = {
        "base_version": 0,
        "intent": "create",
        "operations": [
            {
                "op": "replace",
                "path": "/",
                "value": empty_scene_document(),
                "evidence": "create scene",
            }
        ],
        "touched_paths": ["/"],
    }

    amended = _append_required_facts(
        proposal,
        ["character is pushed against glass", "chest is compressed by glass"],
    )
    document = apply_patch_proposal(
        empty_scene_document(), validate_patch_proposal(amended, 0)
    )

    assert document["requirements"]["required"] == [
        "character is pushed against glass",
        "chest is compressed by glass",
    ]


def test_non_identity_participant_label_survives_normalization():
    document = normalize_scene_document(
        {
            "participants": {
                "glass": {"type": "object", "name": "transparent glass"}
            }
        }
    )

    assert document["participants"]["glass"]["label"] == "transparent glass"


def test_generic_initial_clarification_is_rejected_for_retry():
    assert _is_unhelpful_initial_clarification(
        empty_scene_document(),
        {
            "operations": [],
            "clarification": "您的意图不明确。请说明您想对 SceneDocument 进行的修改。",
        },
    ) is True


def test_specific_initial_clarification_remains_allowed():
    assert _is_unhelpful_initial_clarification(
        empty_scene_document(),
        {
            "operations": [],
            "clarification": "画面中的“她”指左侧角色还是右侧角色？",
        },
    ) is False


def test_ambiguous_fallback_returns_structured_clarification():
    proposal = _fallback_patch(sample_document(version=2), "把她换一下")

    assert proposal["intent"] == "needs_clarification"
    assert proposal["operations"] == []
    assert proposal["clarification"]
    assert proposal["clarification_options"] == []


def test_renderer_and_api_expose_structured_clarification_metadata():
    rendered = render_prompt_node(
        {
            "scene_document": sample_document(version=2),
            "resolved_prompt_ir": {},
            "validation_report": {},
            "clarification_request": "你指的是哪名角色？",
            "clarification_options": ["左侧角色", "右侧角色"],
            "workflow_inputs": {"target_model": "nai_v4"},
        }
    )
    result = extract_workflow_result({"nodes": {"target_renderer": rendered}})

    assert rendered["final_output"]["status"] == "needs_clarification"
    assert result["clarification_request"] == {
        "question": "你指的是哪名角色？",
        "options": ["左侧角色", "右侧角色"],
    }


def test_workflow_result_persists_patch_diagnostics():
    rendered = render_prompt_node(
        {
            "scene_document": sample_document(version=2),
            "resolved_prompt_ir": {},
            "validation_report": {},
            "clarification_request": "请确认方向",
            "workflow_inputs": {"target_model": "nai_v4"},
        }
    )
    result = extract_workflow_result(
        {
            "nodes": {
                "scene_document_editor": {
                    "editor_error": "invalid spatial path",
                    "patch_proposal": {"intent": "correct_direction"},
                },
                "scene_document_processor": {"patch_error": "replace path missing"},
                "target_renderer": rendered,
            }
        }
    )

    assert result["workflow_diagnostics"] == {
        "editor_error": "invalid spatial path",
        "patch_error": "replace path missing",
        "patch_intent": "correct_direction",
    }


def test_explicit_named_character_requires_an_identity_name():
    with pytest.raises(Exception, match="identity.input_name"):
        normalize_scene_document(
            {
                "participants": {
                    "elaina": {
                        "id": "elaina",
                        "type": "named_character",
                        "identity": {"input_name": ""},
                    }
                }
            }
        )


def test_patch_rejects_dangling_relation_for_arbitrary_participant_id():
    document = normalize_scene_document(
        {
            "participants": {
                "elaina": {
                    "type": "named_character",
                    "identity": {"input_name": "Elaina"},
                }
            },
            "relations": {
                "r1": {
                    "subject": "external_hand",
                    "predicate": "push",
                    "object": "elaina",
                }
            },
        },
        version=1,
    )
    proposal = validate_patch_proposal(
        {
            "base_version": 1,
            "operations": [{"op": "remove", "path": "/participants/elaina"}],
        },
        1,
    )

    with pytest.raises(ValueError, match="missing participant 'elaina'"):
        apply_patch_proposal(document, proposal)


@pytest.mark.asyncio
async def test_identity_resolver_ignores_animals_and_roles(monkeypatch):
    def should_not_create_model(**kwargs):
        raise AssertionError("identity model should not run for non-character roles")

    monkeypatch.setattr(
        "app.services.ai_provider.ai_provider.get_model", should_not_create_model
    )
    document = normalize_scene_document(
        {
            "participants": {
                "dog": {"type": "animal", "identity": {}},
                "camera_operator": {"type": "role", "identity": {}},
            }
        },
        version=1,
    )
    result = await resolve_identities_node(
        {
            "identity_context": document,
            "impact_set": {"identity_changed": True},
            "messages": [],
        }
    )

    assert result["identity_terms"] == []


@pytest.mark.asyncio
async def test_identity_resolver_only_recomputes_changed_participants(monkeypatch):
    class OneIdentityModel:
        async def ainvoke(self, messages):
            payload = str(messages[-1].content)
            assert "character_1" in payload
            assert "character_2" not in payload
            return AIMessage(
                content=json.dumps(
                    {
                        "identities": [
                            {
                                "participant_id": "character_1",
                                "input_name": "Moria Luluka",
                                "canonical_name": "Moria Luluka",
                                "series": "test",
                                "danbooru_tag_candidates": ["moria_luluka"],
                            }
                        ]
                    }
                )
            )

    async def resolve_candidates(terms, limit=24):
        return [
            {
                "original": term,
                "normalized_input": term.lower().replace(" ", "_"),
                "name": "moria_luluka",
                "category": 4,
                "post_count": 100,
                "status": "verified",
                "confidence": 1.0,
            }
            for term in terms
        ]

    monkeypatch.setattr(
        "app.services.ai_provider.ai_provider.get_model",
        lambda **kwargs: OneIdentityModel(),
    )
    monkeypatch.setattr(
        "app.agents.prompt_generation.danbooru.resolve_tag_candidates",
        resolve_candidates,
    )
    document = normalize_scene_document(
        {
            "participants": {
                "character_1": {
                    "type": "named_character",
                    "identity": {"input_name": "Moria Luluka"},
                },
                "character_2": {
                    "type": "named_character",
                    "identity": {"input_name": "Megurine Luka"},
                },
            }
        },
        version=2,
    )
    result = await resolve_identities_node(
        {
            "identity_context": document,
            "previous_resolved_prompt_ir": {
                "identity_terms": [
                    {
                        "value": "hatsune_miku",
                        "participant_id": "character_1",
                        "source_path": "/participants/character_1/identity",
                    },
                    {
                        "value": "megurine_luka",
                        "participant_id": "character_2",
                        "source_path": "/participants/character_2/identity",
                    },
                ]
            },
            "impact_set": {
                "identity_changed": True,
                "identity_changed_participant_ids": ["character_1"],
                "identity_deleted_participant_ids": [],
            },
            "messages": [],
        }
    )

    values = [item["value"] for item in result["identity_terms"]]
    assert values == ["megurine_luka", "moria_luluka"]


def test_validator_and_renderer_reject_cjk_prompt_terms():
    document = sample_document()
    prompt_ir = {
        "identity_terms": [],
        "positive_terms": [
            {"value": "手机摄像画面", "source_path": "/composition/camera/0"}
        ],
        "compiled_negative_terms": [],
        "covered_paths": ["/composition/camera/0"],
        "danbooru_tag_records": [],
    }
    validation = validate_prompt_node(
        {
            "scene_document": document,
            "impact_set": {"removed_identity_terms": []},
            "resolved_prompt_ir": prompt_ir,
        }
    )
    assert "non_target_language" in validation["validation_report"]["issue_codes"]

    rendered = render_prompt_node(
        {
            "scene_document": document,
            "resolved_prompt_ir": prompt_ir,
            "validation_report": {"valid": True, "issue_codes": []},
            "workflow_inputs": {"target_model": "nai_v4"},
        }
    )
    assert rendered["final_output"]["status"] == "failed"
    assert rendered["final_output"]["positive_prompt"] is None


@pytest.mark.asyncio
async def test_visual_resolver_normalizes_cjk_phrases_before_prompt_ir(monkeypatch):
    class NormalizingModel:
        def __init__(self):
            self.calls = 0

        async def ainvoke(self, messages):
            self.calls += 1
            if self.calls == 1:
                return AIMessage(
                    content=json.dumps(
                        {
                            "atomic_facts": [
                                {
                                    "source_path": "/composition/camera/0",
                                    "candidates": [],
                                    "fallback_phrase": "手机摄像画面，带菜单栏",
                                }
                            ],
                            "relation_facts": [],
                            "negative_facts": [],
                        },
                        ensure_ascii=False,
                    )
                )
            return AIMessage(
                content=json.dumps(
                    {
                        "atomic_facts": [
                            {
                                "source_path": "/composition/camera/0",
                                "candidates": [],
                                "fallback_phrase": "cellphone camera view with visible UI",
                            }
                        ],
                        "relation_facts": [],
                        "negative_facts": [],
                    }
                )
            )

    model = NormalizingModel()
    monkeypatch.setattr(
        "app.services.ai_provider.ai_provider.get_model", lambda **kwargs: model
    )
    result = await resolve_visual_semantics_node(
        {
            "visual_context": normalize_scene_document(
                {"composition": {"camera": ["手机摄像画面，带菜单栏"]}},
                version=1,
            ),
            "impact_set": {"visual_changed": True},
            "workflow_inputs": {"prompt_strategy": "faithful"},
            "messages": [],
        }
    )

    assert [item["value"] for item in result["atomic_terms"]] == [
        "cellphone camera view with visible UI"
    ]
    assert model.calls == 2


@pytest.mark.asyncio
async def test_visual_resolver_preserves_unaffected_terms_during_local_edit(monkeypatch):
    class LocalEditModel:
        async def ainvoke(self, messages):
            return AIMessage(
                content=json.dumps(
                    {
                        "atomic_facts": [
                            {
                                "source_path": "/composition/lighting/0",
                                "candidates": [],
                                "fallback_phrase": "soft rim lighting",
                            },
                            {
                                "source_path": "/environment/location",
                                "candidates": [],
                                "fallback_phrase": "unwanted changed location",
                            },
                        ],
                        "relation_facts": [],
                        "negative_facts": [],
                    }
                )
            )

    monkeypatch.setattr(
        "app.services.ai_provider.ai_provider.get_model",
        lambda **kwargs: LocalEditModel(),
    )
    result = await resolve_visual_semantics_node(
        {
            "visual_context": normalize_scene_document(
                {
                    "environment": {"location": "street"},
                    "composition": {"lighting": ["soft rim lighting"]},
                },
                version=2,
            ),
            "previous_resolved_prompt_ir": {
                "atomic_terms": [
                    {
                        "value": "street",
                        "kind": "verified_tag",
                        "polarity": "positive",
                        "source_path": "/environment/location",
                    },
                    {
                        "value": "harsh lighting",
                        "kind": "descriptive_phrase",
                        "polarity": "positive",
                        "source_path": "/composition/lighting/0",
                    },
                ],
                "relation_terms": [],
                "negative_terms": [],
            },
            "impact_set": {
                "visual_changed": True,
                "touched_paths": ["/composition/lighting/0"],
            },
            "workflow_inputs": {"prompt_strategy": "faithful"},
            "messages": [],
        }
    )
    values = [item["value"] for item in result["atomic_terms"]]

    assert values == ["street", "soft rim lighting"]

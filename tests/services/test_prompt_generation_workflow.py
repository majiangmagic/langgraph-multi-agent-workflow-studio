"""Tests for the SceneDocument-based prompt generation workflow."""

from __future__ import annotations

import json
import uuid

import pytest
from langchain_core.messages import AIMessage

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
from app.agents.prompt_generation.scene_document_processor.nodes import apply_patch_node
from app.agents.prompt_generation.visual_semantic_resolver.nodes import (
    resolve_visual_semantics_node,
)
from app.api.routes.conversation import extract_workflow_memory
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


def test_identity_only_change_does_not_invalidate_visual_resolution():
    previous = sample_document()
    current = sample_document("Moria Luluka", version=2)

    impact = compute_impact_set(previous, current)

    assert impact["identity_changed"] is True
    assert impact["visual_changed"] is False
    assert "Hatsune Miku" in impact["removed_identity_terms"]


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
            "scene_document": normalize_scene_document(
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
            "scene_document": normalize_scene_document(
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
            "scene_document": sample_document(),
            "impact_set": {"identity_changed": True},
            "workflow_inputs": {},
            "messages": [],
        }
    )

    assert result["identity_terms"][0]["value"] == "hatsune_miku"
    assert result["identity_terms"][0]["kind"] == "verified_identity_tag"
    assert model.calls == 2
    assert result["identity_tag_adjudication"]["triggered"] is True


class WorkflowModel:
    """Deterministic structured responses for two workflow turns."""

    async def ainvoke(self, messages):
        system = str(messages[0].content)
        payload = str(messages[-1].content)
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
            "scene_document": document,
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
            "scene_document": document,
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
            "scene_document": normalize_scene_document(
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
            "scene_document": normalize_scene_document(
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

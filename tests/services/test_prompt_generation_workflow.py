"""Tests for the DSL-driven prompt generation workflow."""

from langchain_core.messages import AIMessage, HumanMessage
import pytest

from app.agents.prompt_generation.natural_language_editor.nodes import resolve_node
from app.agents.prompt_generation.requirement_analyzer.nodes import (
    analyze_node,
    detect_target_model,
)
from app.agents.prompt_generation.character_prompt_generator.nodes import (
    filter_character_records,
)
from app.agents.prompt_generation.format_optimizer.nodes import optimize_format_node
from app.agents.prompt_generation.prompt_aggregator.nodes import aggregate_prompt_node
from app.agents.prompt_generation.danbooru import (
    generate_search_terms,
    verified_tags_from_records,
)
from app.core.langgraph.workflows.prompt_generation_workflow.graph import (
    create_prompt_generation_workflow_graph,
)
from app.core.langgraph.workflows.prompt_generation_workflow.state import build_initial_state
from app.services.ai_provider import AIProvider


def prompt_generation_agents():
    names = [
        "official_supervisor",
        "natural_language_editor",
        "prompt_requirement_analyzer",
        "character_prompt_generator",
        "scene_prompt_generator",
        "additional_prompt_generator",
        "prompt_aggregator",
        "prompt_format_optimizer",
    ]
    return [
        {
            "id": f"agent-{name}",
            "name": name,
            "description": f"Runtime config for {name}.",
            "system_prompt": f"Run {name}.",
            "model": "test-model",
            "temperature": 0.2,
            "tools": [],
        }
        for name in names
    ]


def test_nai_version_detection_accepts_ui_and_natural_language_forms():
    assert detect_target_model("目标模型：nai_v3") == "nai_v3"
    assert detect_target_model("use NAI V4") == "nai_v4"
    assert detect_target_model("未指定模型") == "nai_v4"


def patch_model_nodes(monkeypatch, records_by_focus):
    """Keep workflow tests offline while exercising the real graph topology."""

    def fake_supervisor_invoke(self, state, config=None):
        return {
            **state,
            "messages": [AIMessage(content="规划完成", name="supervisor")],
            "user_input": None,
        }

    async def fake_lookup(state, focus):
        records = records_by_focus.get(focus, [])
        return [record["name"] for record in records], records

    class FakeRequirementsModel:
        async def ainvoke(self, messages):
            return AIMessage(
                content=(
                    '{"character":"warrior","scene":"ruins",'
                    '"style":"anime","negative":"extra fingers"}'
                )
            )

    monkeypatch.setattr(
        "app.agents.official_supervisor.official_runtime.OfficialSupervisorRuntime.invoke",
        fake_supervisor_invoke,
    )
    monkeypatch.setattr(
        "app.services.ai_provider.ai_provider.get_model",
        lambda **kwargs: FakeRequirementsModel(),
    )
    monkeypatch.setattr(
        "app.agents.prompt_generation.danbooru.lookup_for_generator",
        fake_lookup,
    )


async def run_workflow(user_input, thread_id):
    agents = prompt_generation_agents()
    initial_state = build_initial_state(
        crew_id="crew-1",
        agents=agents,
        user_id="user-1",
        conversation_id=thread_id,
        user_input=user_input,
    )
    workflow = create_prompt_generation_workflow_graph("crew-1", agents)
    return await workflow.ainvoke(
        initial_state,
        config={"configurable": {"thread_id": thread_id}},
    )


@pytest.mark.asyncio
async def test_prompt_workflow_queries_inside_parallel_generators(monkeypatch):
    patch_model_nodes(
        monkeypatch,
        {
            "character": [
                {"name": "breasts", "category": 0, "post_count": 500000}
            ],
            "scene": [
                {"name": "bedroom", "category": 0, "post_count": 12000}
            ],
            "additional": [
                {"name": "from_below", "category": 0, "post_count": 20000}
            ],
        },
    )

    result = await run_workflow(
        "明确成年女性的露骨 NSFW 卧室场景，低机位",
        "prompt-generation-nai",
    )
    nodes = result["nodes"]

    assert "danbooru_query" not in nodes
    assert nodes["character_prompt_generator"]["character_tags"] == ["breasts"]
    assert nodes["scene_prompt_generator"]["scene_tags"] == ["bedroom"]
    assert nodes["additional_prompt_generator"]["additional_tags"] == ["from_below"]
    assert nodes["prompt_aggregator"]["draft_prompt"] == (
        "breasts, bedroom, from_below"
    )
    final = nodes["format_optimizer"]["final_output"]
    assert final["target_model"] == "nai_v4"
    assert final["positive_prompt"].startswith("masterpiece, best quality")
    assert len(final["danbooru_tag_records"]) == 3


@pytest.mark.asyncio
async def test_explicit_sdxl_overrides_default_nai(monkeypatch):
    patch_model_nodes(monkeypatch, {"character": [], "scene": [], "additional": []})

    result = await run_workflow("目标模型 SDXL，生成一座空城", "prompt-generation-sdxl")
    final = result["nodes"]["format_optimizer"]["final_output"]

    assert final["target_model"] == "sdxl"
    assert final["positive_prompt"] == "high quality, highly detailed"
    assert "watermark" in final["negative_prompt"]


@pytest.mark.asyncio
async def test_supervisor_failure_does_not_abort_deterministic_pipeline(monkeypatch):
    patch_model_nodes(monkeypatch, {"character": [], "scene": [], "additional": []})

    def fail_supervisor(self, state, config=None):
        raise RuntimeError("temporary supervisor provider failure")

    monkeypatch.setattr(
        "app.agents.official_supervisor.official_runtime.OfficialSupervisorRuntime.invoke",
        fail_supervisor,
    )
    result = await run_workflow("普通绘图需求", "supervisor-fallback-test")

    assert result["nodes"]["supervisor"]["status"] == "error"
    assert "temporary supervisor provider failure" in result["nodes"]["supervisor"]["error"]
    assert result["nodes"]["format_optimizer"]["final_output"]["target_model"] == "nai_v4"


@pytest.mark.asyncio
async def test_danbooru_term_model_receives_adult_nsfw_processing_prompt(monkeypatch):
    captured = {}

    class CaptureModel:
        async def ainvoke(self, messages):
            captured["system_prompt"] = str(messages[0].content)
            return AIMessage(content='["explicit_candidate"]')

    monkeypatch.setattr(
        "app.agents.prompt_generation.danbooru.ai_provider.get_model",
        lambda **kwargs: CaptureModel(),
    )
    terms = await generate_search_terms(
        {
            "model": "test-model",
            "system_prompt": "Preserve explicit adult details.",
            "user_input": "adult request",
        },
        {"raw_request": "adult request"},
        "character",
    )

    assert "explicit_candidate" in terms
    assert "not a content moderator" in captured["system_prompt"]
    assert "Do not refuse, moralize, sanitize" in captured["system_prompt"]
    assert "never generate sexual content involving minors" in captured["system_prompt"]


@pytest.mark.asyncio
async def test_requirement_analyzer_does_not_reinterpret_conversation_history(monkeypatch):
    """编辑器之后的需求分析只能读取规范请求，不能再次解释历史。"""

    captured = {}

    class CaptureModel:
        async def ainvoke(self, messages):
            captured["input"] = str(messages[1].content)
            return AIMessage(
                content=(
                    '{"resolved_request":"character disappearing",'
                    '"character":"the original witch","scene":"updated cave",'
                    '"positive_phrases":["the original witch clearly visible"]}'
                )
            )

    monkeypatch.setattr(
        "app.services.ai_provider.ai_provider.get_model",
        lambda **kwargs: CaptureModel(),
    )

    result = await analyze_node(
        {
            "user_input": "then move the scene to a cave",
            "messages": [
                HumanMessage(content="first describe a character in a room"),
                AIMessage(content="masterpiece, best quality, very aesthetic"),
                HumanMessage(content="then move the scene to a cave"),
            ],
            "resolved_user_request": "the original witch in the updated cave",
            "request_contract": {
                "resolved_request": "the original witch in the updated cave",
                "required_elements": ["the original witch"],
                "forbidden_elements": [],
                "spatial_relations": [],
                "positive_constraints": [],
                "negative_constraints": [],
            },
            "editor_succeeded": True,
            "system_prompt": "Analyze the request.",
            "model": "test-model",
            "temperature": 0.2,
        }
    )

    assert "Authoritative request contract:" in captured["input"]
    assert "first describe a character in a room" not in captured["input"]
    assert "then move the scene to a cave" not in captured["input"]
    assert "masterpiece, best quality, very aesthetic" not in captured["input"]
    assert result["requirements_json"]["character"] == "the original witch"
    assert result["requirements_json"]["scene"] == "updated cave"
    assert result["requirements_json"]["latest_user_input"] == "then move the scene to a cave"
    assert result["requirements_json"]["raw_request"] == (
        "the original witch in the updated cave"
    )


@pytest.mark.asyncio
async def test_natural_language_editor_resolves_colloquial_edit_without_prompt_feedback(
    monkeypatch,
):
    """口语理解层应维护完整请求，同时忽略上一轮生成的 Prompt。"""

    captured = {}

    class EditorModel:
        async def ainvoke(self, messages):
            captured["system"] = str(messages[0].content)
            captured["input"] = str(messages[1].content)
            return AIMessage(
                content=(
                    '{"turn_intent":"restore_and_confirm",'
                    '"edit_operations":[{"op":"retain","target":"character",'
                    '"value":"the original witch","evidence":"still the witch?"}],'
                    '"resolved_user_request":"the original witch in the updated cave",'
                    '"request_contract":{"resolved_request":'
                    '"the original witch in the updated cave",'
                    '"required_elements":["the original witch"],'
                    '"forbidden_elements":[],"spatial_relations":[], '
                    '"positive_constraints":[],"negative_constraints":[]}}'
                )
            )

    monkeypatch.setattr(
        "app.services.ai_provider.ai_provider.get_model",
        lambda **kwargs: EditorModel(),
    )

    result = await resolve_node(
        {
            "user_input": "still the witch?",
            "messages": [
                HumanMessage(content="the witch in a room"),
                AIMessage(content="masterpiece, best quality, unrelated_tag"),
                HumanMessage(content="move the scene to a cave"),
                HumanMessage(content="still the witch?"),
            ],
            "system_prompt": "Resolve ordinary conversational edits.",
            "model": "test-model",
            "temperature": 0.1,
        }
    )

    assert "the witch in a room" in captured["input"]
    assert "move the scene to a cave" in captured["input"]
    assert "masterpiece, best quality, unrelated_tag" not in captured["input"]
    assert "具体短语" in captured["system"]
    assert result["turn_intent"] == "restore_and_confirm"
    assert result["editor_succeeded"] is True
    assert result["resolved_user_request"] == (
        "the original witch in the updated cave"
    )
    assert result["request_contract"]["required_elements"] == [
        "the original witch"
    ]


@pytest.mark.asyncio
async def test_natural_language_editor_inherits_anchors_omitted_by_model(monkeypatch):
    """后续模型即使漏字段，也不能让既有角色、禁止项和空间关系消失。"""

    previous_contract = {
        "resolved_request": "the witch in a cave",
        "required_elements": ["the witch"],
        "forbidden_elements": ["floating props"],
        "spatial_relations": ["vines extend from cave walls"],
        "positive_constraints": [],
        "negative_constraints": [],
    }

    class ForgetfulModel:
        async def ainvoke(self, messages):
            return AIMessage(
                content=(
                    '{"turn_intent":"restore_visibility","edit_operations":[],'
                    '"resolved_user_request":"the cave remains",'
                    '"request_contract":{"resolved_request":"the cave remains",'
                    '"required_elements":[],"forbidden_elements":[],'
                    '"spatial_relations":[],"positive_constraints":[],'
                    '"negative_constraints":[]}}'
                )
            )

    monkeypatch.setattr(
        "app.services.ai_provider.ai_provider.get_model",
        lambda **kwargs: ForgetfulModel(),
    )
    result = await resolve_node(
        {
            "user_input": "the witch disappeared",
            "messages": [
                AIMessage(
                    content="previous output",
                    additional_kwargs={
                        "workflow_memory": {"request_contract": previous_contract}
                    },
                ),
                HumanMessage(content="the witch disappeared"),
            ],
            "system_prompt": "Resolve edits.",
            "model": "test-model",
            "temperature": 0.1,
        }
    )

    contract = result["request_contract"]
    assert contract["required_elements"] == ["the witch"]
    assert contract["forbidden_elements"] == ["floating props"]
    assert contract["spatial_relations"] == ["vines extend from cave walls"]
    assert "the witch" in result["resolved_user_request"]


@pytest.mark.asyncio
async def test_natural_language_editor_allows_explicit_anchor_removal(monkeypatch):
    """锚点保护不能阻止用户明确删除已有元素。"""

    class RemovalModel:
        async def ainvoke(self, messages):
            return AIMessage(
                content=(
                    '{"turn_intent":"remove","edit_operations":['
                    '{"op":"remove","target":"the witch","value":""}],'
                    '"resolved_user_request":"an empty cave",'
                    '"request_contract":{"resolved_request":"an empty cave",'
                    '"required_elements":[],"forbidden_elements":[],'
                    '"spatial_relations":[],"positive_constraints":[],'
                    '"negative_constraints":[]}}'
                )
            )

    monkeypatch.setattr(
        "app.services.ai_provider.ai_provider.get_model",
        lambda **kwargs: RemovalModel(),
    )
    result = await resolve_node(
        {
            "user_input": "remove the witch",
            "messages": [
                AIMessage(
                    content="previous output",
                    additional_kwargs={
                        "workflow_memory": {
                            "request_contract": {
                                "resolved_request": "the witch in a cave",
                                "required_elements": ["the witch"],
                                "forbidden_elements": [],
                                "spatial_relations": [],
                                "positive_constraints": [],
                                "negative_constraints": [],
                            }
                        }
                    },
                ),
                HumanMessage(content="remove the witch"),
            ],
            "system_prompt": "Resolve edits.",
            "model": "test-model",
            "temperature": 0.1,
        }
    )

    assert result["request_contract"]["required_elements"] == []
    assert result["resolved_user_request"] == "an empty cave"


@pytest.mark.asyncio
async def test_destructive_edit_is_reviewed_by_supervisor_model(monkeypatch):
    """快速模型尝试破坏锚点时，必须经过强模型语义复核。"""

    calls = []

    class FastModel:
        async def ainvoke(self, messages):
            return AIMessage(
                content=(
                    '{"turn_intent":"remove","edit_operations":['
                    '{"op":"remove","target":"the witch","value":""}],'
                    '"resolved_user_request":"an empty cave",'
                    '"request_contract":{"resolved_request":"an empty cave",'
                    '"required_elements":[],"forbidden_elements":[],'
                    '"spatial_relations":[],"positive_constraints":[],'
                    '"negative_constraints":[]}}'
                )
            )

    class ReviewModel:
        async def ainvoke(self, messages):
            return AIMessage(
                content=(
                    '{"turn_intent":"restore","edit_operations":['
                    '{"op":"retain","target":"the witch","value":"visible"}],'
                    '"resolved_user_request":"the witch clearly visible in the cave",'
                    '"request_contract":{"resolved_request":'
                    '"the witch clearly visible in the cave",'
                    '"required_elements":["the witch"],"forbidden_elements":[],'
                    '"spatial_relations":[],"positive_constraints":[],'
                    '"negative_constraints":[]}}'
                )
            )

    def model_factory(**kwargs):
        calls.append(kwargs["model_name"])
        return ReviewModel() if kwargs["model_name"] != "fast-model" else FastModel()

    monkeypatch.setattr(
        "app.services.ai_provider.ai_provider.get_model",
        model_factory,
    )
    result = await resolve_node(
        {
            "user_input": "the witch is missing",
            "messages": [
                AIMessage(
                    content="previous output",
                    additional_kwargs={
                        "workflow_memory": {
                            "request_contract": {
                                "resolved_request": "the witch in a cave",
                                "required_elements": ["the witch"],
                                "forbidden_elements": [],
                                "spatial_relations": [],
                                "positive_constraints": [],
                                "negative_constraints": [],
                            }
                        }
                    },
                ),
                HumanMessage(content="the witch is missing"),
            ],
            "system_prompt": "Resolve edits.",
            "model": "fast-model",
            "temperature": 0.1,
        }
    )

    assert calls == ["fast-model", AIProvider.SUPERVISOR_MODEL]
    assert result["request_contract"]["required_elements"] == ["the witch"]
    assert result["resolved_user_request"] == "the witch clearly visible in the cave"


@pytest.mark.asyncio
async def test_requirement_analyzer_prefers_editor_resolved_request(monkeypatch):
    """需求分析只拆分完整请求，不应把最后一句口语当成完整需求。"""

    captured = {}

    class AnalyzerModel:
        async def ainvoke(self, messages):
            captured["input"] = str(messages[1].content)
            return AIMessage(
                content=(
                    '{"resolved_request":"the original witch in the updated cave",'
                    '"character":"the original witch","scene":"updated cave"}'
                )
            )

    monkeypatch.setattr(
        "app.services.ai_provider.ai_provider.get_model",
        lambda **kwargs: AnalyzerModel(),
    )

    result = await analyze_node(
        {
            "user_input": "still the witch?",
            "messages": [HumanMessage(content="still the witch?")],
            "resolved_user_request": "the original witch in the updated cave",
            "request_contract": {
                "resolved_request": "the original witch in the updated cave",
                "required_elements": ["the original witch"],
                "forbidden_elements": [],
                "spatial_relations": [],
                "positive_constraints": [],
                "negative_constraints": [],
            },
            "editor_succeeded": True,
            "system_prompt": "Split the complete request.",
            "model": "test-model",
            "temperature": 0.2,
        }
    )

    assert "Authoritative resolved request:\nthe original witch in the updated cave" in captured[
        "input"
    ]
    assert "still the witch?" not in captured["input"]
    assert result["requirements_json"]["character"] == "the original witch"
    assert result["requirements_json"]["latest_user_input"] == "still the witch?"


@pytest.mark.asyncio
async def test_danbooru_term_model_receives_resolved_request(monkeypatch):
    """Danbooru expansion should use the resolved request, not only the latest turn."""

    captured = {}

    class CaptureModel:
        async def ainvoke(self, messages):
            captured["request"] = str(messages[1].content)
            return AIMessage(content='["updated_cave"]')

    monkeypatch.setattr(
        "app.agents.prompt_generation.danbooru.ai_provider.get_model",
        lambda **kwargs: CaptureModel(),
    )

    terms = await generate_search_terms(
        {"model": "test-model", "system_prompt": "", "user_input": "change the scene"},
        {
            "resolved_request": "same character in updated cave",
            "latest_user_input": "change the scene",
            "character": "same character",
            "scene": "updated cave",
        },
        "scene",
    )

    assert "resolved_request: same character in updated cave" in captured["request"]
    assert "scene: updated cave" in captured["request"]
    assert "updated_cave" in terms


@pytest.mark.asyncio
async def test_danbooru_terms_filter_prompt_quality_noise(monkeypatch):
    """Default prompt quality words should not become Danbooru lookup terms."""

    class NoisyModel:
        async def ainvoke(self, messages):
            return AIMessage(
                content='["best quality", "very aesthetic", "tentacle cave"]'
            )

    monkeypatch.setattr(
        "app.agents.prompt_generation.danbooru.ai_provider.get_model",
        lambda **kwargs: NoisyModel(),
    )

    terms = await generate_search_terms(
        {"model": "test-model", "system_prompt": "", "user_input": ""},
        {
            "resolved_request": "masterpiece, best quality, very aesthetic, tentacle cave",
            "scene": "tentacle cave",
        },
        "scene",
    )

    normalized = {term.replace(" ", "_").lower() for term in terms}
    assert "best_quality" not in normalized
    assert "very_aesthetic" not in normalized
    assert "quality" not in normalized
    assert "tentacle_cave" in normalized


def test_only_verified_records_become_final_tags():
    """模型候选只用于查询，未验证词不得冒充最终 Danbooru 标签。"""

    tags = verified_tags_from_records(
        [{"name": "cave", "category": 0, "post_count": 12000}],
    )

    assert tags == ["cave"]


def test_named_character_identity_rejects_unrelated_existing_character_tag():
    """An existing Danbooru character tag is not proof that it is the requested person."""

    records = filter_character_records(
        [
            {"name": "irena", "category": 4, "post_count": 20},
            {
                "name": "elaina_(majo_no_tabitabi)",
                "category": 4,
                "post_count": 1000,
            },
            {"name": "white_hair", "category": 0, "post_count": 500000},
        ],
        {
            "character_identities": [
                {
                    "original_name": "伊蕾娜",
                    "canonical_name": "Elaina",
                    "series": "Majo no Tabitabi",
                    "danbooru_tag": "elaina_(majo_no_tabitabi)",
                }
            ]
        },
    )

    assert [record["name"] for record in records] == [
        "elaina_(majo_no_tabitabi)",
        "white_hair",
    ]


def test_nai_v4_keeps_relations_while_nai_v3_emits_verified_tags_only():
    base_state = {
        "requirements_json": {},
        "prompt_sections": {
            "character": ["elaina_(majo_no_tabitabi)"],
            "scene": ["cave"],
            "additional": [],
            "descriptive_phrases": ["tentacles continuously extend from the cave walls"],
        },
        "negative_prompt": "",
        "danbooru_tag_records": [],
    }

    v4 = optimize_format_node({**base_state, "target_model": "nai_v4"})
    v3 = optimize_format_node({**base_state, "target_model": "nai_v3"})

    assert "elaina_(majo_no_tabitabi)" in v4["formatted_prompt"]
    assert "tentacles continuously extend from the cave walls" in v4["formatted_prompt"]
    assert "elaina_(majo_no_tabitabi)" in v3["formatted_prompt"]
    assert "tentacles continuously extend from the cave walls" not in v3["formatted_prompt"]


def test_aggregator_separates_relations_negatives_and_unverified_candidates():
    """关系描述需要保留，否定句和未验证候选不能污染正向标签。"""

    result = aggregate_prompt_node(
        {
            "character_tags": ["elaina_(majo_no_tabitabi)"],
            "scene_tags": ["cave"],
            "additional_tags": [],
            "danbooru_search_terms": [
                "elaina_(majo_no_tabitabi)",
                "cave",
                "appearing_from_nowhere",
            ],
            "danbooru_tag_records": [
                {"name": "elaina_(majo_no_tabitabi)", "post_count": 1000},
                {"name": "cave", "post_count": 2000},
            ],
            "requirements_json": {
                "positive_phrases": [
                    "Elaina clearly visible",
                    "tentacles continuously extending from the cave walls",
                    "avoid floating disconnected tentacles",
                ],
                "negative_phrases": ["floating disconnected tentacles"],
                "required_elements": ["Elaina"],
                "forbidden_elements": ["disconnected tentacles"],
                "spatial_relations": ["tentacles originate from cave walls"],
            },
        }
    )

    assert "Elaina clearly visible" in result["draft_prompt"]
    assert "tentacles continuously extending from the cave walls" in result[
        "draft_prompt"
    ]
    assert "appearing_from_nowhere" not in result["draft_prompt"]
    assert "avoid floating disconnected tentacles" not in result["draft_prompt"]
    assert "floating disconnected tentacles" in result["negative_prompt"]
    assert "avoid floating disconnected tentacles" not in result["negative_prompt"]
    report = result["consistency_report"]
    assert "appearing_from_nowhere" in report["unverified_candidates_excluded"]

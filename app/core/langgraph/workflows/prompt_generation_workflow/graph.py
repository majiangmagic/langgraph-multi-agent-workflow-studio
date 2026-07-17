"""Graph factory for the prompt_generation_workflow workflow."""

from typing import Any, Dict, List

from app.agents.prompt_generation.character_identity_resolver.graph import create_graph as create_prompt_generation_character_identity_resolver_graph
from app.agents.prompt_generation.prompt_compiler.graph import create_graph as create_prompt_generation_prompt_compiler_graph
from app.agents.prompt_generation.prompt_consistency_validator.graph import create_graph as create_prompt_generation_prompt_consistency_validator_graph
from app.agents.prompt_generation.prompt_impact_router.graph import create_graph as create_prompt_generation_prompt_impact_router_graph
from app.agents.prompt_generation.prompt_semantic_repairer.graph import create_graph as create_prompt_generation_prompt_semantic_repairer_graph
from app.agents.prompt_generation.prompt_target_renderer.graph import create_graph as create_prompt_generation_prompt_target_renderer_graph
from app.agents.prompt_generation.scene_document_editor.graph import create_graph as create_prompt_generation_scene_document_editor_graph
from app.agents.prompt_generation.scene_document_processor.graph import create_graph as create_prompt_generation_scene_document_processor_graph
from app.agents.prompt_generation.visual_semantic_resolver.graph import create_graph as create_prompt_generation_visual_semantic_resolver_graph
from langgraph.graph import END, StateGraph
from app.core.langgraph.workflows.adapters.agent import create_pipeline_context_extension
from app.core.langgraph.workflows.adapters.routing import create_state_condition_router
from app.core.langgraph.checkpoint import get_checkpointer
from app.core.langgraph.store import get_store
from app.core.langgraph.workflows.adapters.agent import create_agent_node
from app.core.langgraph.workflows.registry import workflow_registry
from app.core.langgraph.workflows.prompt_generation_workflow.state import (
    PromptGenerationWorkflowState,
    build_initial_state,
)

WORKFLOW_NAME = "prompt_generation_workflow"
WORKFLOW_METADATA = {'entrypoint': 'scene_document_editor', 'nodes': [{'name': 'scene_document_editor', 'agent': 'scene_document_editor', 'display_name': '解析画面需求', 'on_error': 'fail'}, {'name': 'scene_document_processor', 'agent': 'scene_document_processor', 'display_name': '构建画面工程', 'on_error': 'fail', 'inputs': {'scene_document': 'scene_document_editor.scene_document', 'previous_scene_document': 'scene_document_editor.previous_scene_document', 'previous_resolved_prompt_ir': 'scene_document_editor.previous_resolved_prompt_ir', 'patch_proposal': 'scene_document_editor.patch_proposal', 'clarification_request': 'scene_document_editor.clarification_request'}}, {'name': 'identity_impact_router', 'agent': 'prompt_impact_router', 'display_name': '判断身份变化', 'on_error': 'fail', 'state_agent': 'prompt_impact_router', 'inputs': {'impact_set': 'scene_document_processor.impact_set'}}, {'name': 'character_identity_resolver', 'agent': 'character_identity_resolver', 'display_name': '解析角色身份', 'on_error': 'fail', 'inputs': {'scene_document': 'scene_document_processor.scene_document', 'previous_resolved_prompt_ir': 'scene_document_processor.previous_resolved_prompt_ir', 'impact_set': 'scene_document_processor.impact_set'}}, {'name': 'visual_impact_router', 'agent': 'prompt_impact_router', 'display_name': '判断视觉变化', 'on_error': 'fail', 'state_agent': 'prompt_impact_router', 'inputs': {'impact_set': 'scene_document_processor.impact_set'}}, {'name': 'visual_semantic_resolver', 'agent': 'visual_semantic_resolver', 'display_name': '解析视觉语义', 'on_error': 'fail', 'inputs': {'scene_document': 'scene_document_processor.scene_document', 'previous_resolved_prompt_ir': 'scene_document_processor.previous_resolved_prompt_ir', 'impact_set': 'scene_document_processor.impact_set'}}, {'name': 'prompt_compiler', 'agent': 'prompt_compiler', 'display_name': '编译 Prompt IR', 'on_error': 'fail', 'inputs': {'scene_document': 'scene_document_processor.scene_document', 'impact_set': 'scene_document_processor.impact_set', 'previous_resolved_prompt_ir': 'scene_document_processor.previous_resolved_prompt_ir', 'identity_terms': 'character_identity_resolver.identity_terms', 'identity_tag_records': 'character_identity_resolver.identity_tag_records', 'identity_tag_resolutions': 'character_identity_resolver.identity_tag_resolutions', 'identity_tag_adjudication': 'character_identity_resolver.identity_tag_adjudication', 'visual_search_terms': 'visual_semantic_resolver.visual_search_terms', 'atomic_terms': 'visual_semantic_resolver.atomic_terms', 'relation_terms': 'visual_semantic_resolver.relation_terms', 'negative_terms': 'visual_semantic_resolver.negative_terms', 'visual_tag_records': 'visual_semantic_resolver.visual_tag_records', 'visual_tag_resolutions': 'visual_semantic_resolver.visual_tag_resolutions', 'visual_tag_adjudication': 'visual_semantic_resolver.visual_tag_adjudication', 'repair_overlay': 'semantic_repairer.repair_overlay'}}, {'name': 'consistency_validator', 'agent': 'prompt_consistency_validator', 'display_name': '检查一致性', 'on_error': 'fail', 'inputs': {'scene_document': 'scene_document_processor.scene_document', 'impact_set': 'scene_document_processor.impact_set', 'resolved_prompt_ir': 'prompt_compiler.resolved_prompt_ir'}}, {'name': 'semantic_repairer', 'agent': 'prompt_semantic_repairer', 'display_name': '定向修复', 'on_error': 'fail', 'inputs': {'scene_document': 'scene_document_processor.scene_document', 'resolved_prompt_ir': 'prompt_compiler.resolved_prompt_ir', 'validation_report': 'consistency_validator.validation_report'}}, {'name': 'target_renderer', 'agent': 'prompt_target_renderer', 'display_name': '渲染并校验输出', 'on_error': 'fail', 'inputs': {'scene_document': 'scene_document_processor.scene_document', 'resolved_prompt_ir': 'prompt_compiler.resolved_prompt_ir', 'validation_report': 'consistency_validator.validation_report', 'clarification_request': 'scene_document_processor.clarification_request'}}], 'edges': [{'from': 'scene_document_editor', 'to': 'scene_document_processor'}, {'from': 'character_identity_resolver', 'to': 'visual_impact_router'}, {'from': 'visual_semantic_resolver', 'to': 'prompt_compiler'}, {'from': 'prompt_compiler', 'to': 'consistency_validator'}, {'from': 'semantic_repairer', 'to': 'prompt_compiler'}, {'from': 'target_renderer', 'to': 'END'}, {'from': 'scene_document_processor', 'to': 'identity_impact_router', 'conditional': True, 'branch': 'then', 'condition': {'path': 'nodes.scene_document_processor.document_valid', 'operator': 'equals', 'value': True}}, {'from': 'scene_document_processor', 'to': 'target_renderer', 'conditional': True, 'branch': 'otherwise'}, {'from': 'identity_impact_router', 'to': 'character_identity_resolver', 'conditional': True, 'branch': 'then', 'condition': {'path': 'nodes.identity_impact_router.should_resolve_identity', 'operator': 'equals', 'value': True}}, {'from': 'identity_impact_router', 'to': 'visual_impact_router', 'conditional': True, 'branch': 'otherwise'}, {'from': 'visual_impact_router', 'to': 'visual_semantic_resolver', 'conditional': True, 'branch': 'then', 'condition': {'path': 'nodes.visual_impact_router.should_resolve_visual', 'operator': 'equals', 'value': True}}, {'from': 'visual_impact_router', 'to': 'prompt_compiler', 'conditional': True, 'branch': 'otherwise'}, {'from': 'consistency_validator', 'to': 'semantic_repairer', 'conditional': True, 'branch': 'then', 'condition': {'path': 'nodes.consistency_validator.needs_repair', 'operator': 'equals', 'value': True}, 'loop': {'counter_path': 'nodes.semantic_repairer.repair_attempts', 'max_iterations': 1, 'exhausted': 'target_renderer'}}, {'from': 'consistency_validator', 'to': 'target_renderer', 'conditional': True, 'branch': 'otherwise'}], 'ui': {'title': '图像提示词工程', 'description': '持续编辑结构化画面，并编译为目标生图模型可用的 Prompt', 'input_placeholder': '描述画面，或继续修改人物、动作、关系、场景与构图……', 'input_hint': '支持多轮修改；未指定时使用 NAI V4', 'controls': [{'key': 'prompt_strategy', 'label': '提示策略', 'type': 'segmented', 'default': 'expressive', 'options': [{'value': 'expressive', 'label': '积极扩写'}, {'value': 'faithful', 'label': '保守还原'}]}, {'key': 'target_model', 'label': '目标模型', 'type': 'select', 'default': 'nai_v4', 'options': [{'value': 'nai_v4', 'label': 'NAI V4（混合提示）'}, {'value': 'nai_v3', 'label': 'NAI V3（标签优先）'}, {'value': 'sdxl', 'label': 'SDXL'}, {'value': 'illustrious', 'label': 'Illustrious / 光辉'}, {'value': 'pony', 'label': 'Pony'}, {'value': 'flux', 'label': 'Flux'}, {'value': 'auto', 'label': '从需求识别'}]}]}}


def create_prompt_generation_workflow_graph(
    crew_id: str,
    agents: List[Dict[str, Any]],
):
    """Create this workflow with native LangGraph primitives."""

    workflow = StateGraph(PromptGenerationWorkflowState)
    workflow.add_node(
        "scene_document_editor",
        create_agent_node(
            "scene_document_editor",
            create_prompt_generation_scene_document_editor_graph(),
            extension=create_pipeline_context_extension("scene_document_editor"),
        ),
    )
    workflow.add_node(
        "scene_document_processor",
        create_agent_node(
            "scene_document_processor",
            create_prompt_generation_scene_document_processor_graph(),
            extension=create_pipeline_context_extension("scene_document_processor", inputs={'scene_document': 'scene_document_editor.scene_document', 'previous_scene_document': 'scene_document_editor.previous_scene_document', 'previous_resolved_prompt_ir': 'scene_document_editor.previous_resolved_prompt_ir', 'patch_proposal': 'scene_document_editor.patch_proposal', 'clarification_request': 'scene_document_editor.clarification_request'}),
        ),
    )
    workflow.add_node(
        "identity_impact_router",
        create_agent_node(
            "identity_impact_router",
            create_prompt_generation_prompt_impact_router_graph(),
            extension=create_pipeline_context_extension("identity_impact_router", inputs={'impact_set': 'scene_document_processor.impact_set'}),
        ),
    )
    workflow.add_node(
        "character_identity_resolver",
        create_agent_node(
            "character_identity_resolver",
            create_prompt_generation_character_identity_resolver_graph(),
            extension=create_pipeline_context_extension("character_identity_resolver", inputs={'scene_document': 'scene_document_processor.scene_document', 'previous_resolved_prompt_ir': 'scene_document_processor.previous_resolved_prompt_ir', 'impact_set': 'scene_document_processor.impact_set'}),
        ),
    )
    workflow.add_node(
        "visual_impact_router",
        create_agent_node(
            "visual_impact_router",
            create_prompt_generation_prompt_impact_router_graph(),
            extension=create_pipeline_context_extension("visual_impact_router", inputs={'impact_set': 'scene_document_processor.impact_set'}),
        ),
    )
    workflow.add_node(
        "visual_semantic_resolver",
        create_agent_node(
            "visual_semantic_resolver",
            create_prompt_generation_visual_semantic_resolver_graph(),
            extension=create_pipeline_context_extension("visual_semantic_resolver", inputs={'scene_document': 'scene_document_processor.scene_document', 'previous_resolved_prompt_ir': 'scene_document_processor.previous_resolved_prompt_ir', 'impact_set': 'scene_document_processor.impact_set'}),
        ),
    )
    workflow.add_node(
        "prompt_compiler",
        create_agent_node(
            "prompt_compiler",
            create_prompt_generation_prompt_compiler_graph(),
            extension=create_pipeline_context_extension("prompt_compiler", inputs={'scene_document': 'scene_document_processor.scene_document', 'impact_set': 'scene_document_processor.impact_set', 'previous_resolved_prompt_ir': 'scene_document_processor.previous_resolved_prompt_ir', 'identity_terms': 'character_identity_resolver.identity_terms', 'identity_tag_records': 'character_identity_resolver.identity_tag_records', 'identity_tag_resolutions': 'character_identity_resolver.identity_tag_resolutions', 'identity_tag_adjudication': 'character_identity_resolver.identity_tag_adjudication', 'visual_search_terms': 'visual_semantic_resolver.visual_search_terms', 'atomic_terms': 'visual_semantic_resolver.atomic_terms', 'relation_terms': 'visual_semantic_resolver.relation_terms', 'negative_terms': 'visual_semantic_resolver.negative_terms', 'visual_tag_records': 'visual_semantic_resolver.visual_tag_records', 'visual_tag_resolutions': 'visual_semantic_resolver.visual_tag_resolutions', 'visual_tag_adjudication': 'visual_semantic_resolver.visual_tag_adjudication', 'repair_overlay': 'semantic_repairer.repair_overlay'}),
        ),
    )
    workflow.add_node(
        "consistency_validator",
        create_agent_node(
            "consistency_validator",
            create_prompt_generation_prompt_consistency_validator_graph(),
            extension=create_pipeline_context_extension("consistency_validator", inputs={'scene_document': 'scene_document_processor.scene_document', 'impact_set': 'scene_document_processor.impact_set', 'resolved_prompt_ir': 'prompt_compiler.resolved_prompt_ir'}),
        ),
    )
    workflow.add_node(
        "semantic_repairer",
        create_agent_node(
            "semantic_repairer",
            create_prompt_generation_prompt_semantic_repairer_graph(),
            extension=create_pipeline_context_extension("semantic_repairer", inputs={'scene_document': 'scene_document_processor.scene_document', 'resolved_prompt_ir': 'prompt_compiler.resolved_prompt_ir', 'validation_report': 'consistency_validator.validation_report'}),
        ),
    )
    workflow.add_node(
        "target_renderer",
        create_agent_node(
            "target_renderer",
            create_prompt_generation_prompt_target_renderer_graph(),
            extension=create_pipeline_context_extension("target_renderer", inputs={'scene_document': 'scene_document_processor.scene_document', 'resolved_prompt_ir': 'prompt_compiler.resolved_prompt_ir', 'validation_report': 'consistency_validator.validation_report', 'clarification_request': 'scene_document_processor.clarification_request'}),
        ),
    )
    workflow.add_edge("scene_document_editor", "scene_document_processor")
    workflow.add_edge("character_identity_resolver", "visual_impact_router")
    workflow.add_edge("visual_semantic_resolver", "prompt_compiler")
    workflow.add_edge("prompt_compiler", "consistency_validator")
    workflow.add_edge("semantic_repairer", "prompt_compiler")
    workflow.add_edge("target_renderer", END)
    workflow.add_conditional_edges(
        'scene_document_processor',
        create_state_condition_router(
            path='nodes.scene_document_processor.document_valid',
            operator='equals',
            expected=True,
            source='scene_document_processor',
            then_target='identity_impact_router',
            otherwise_target='target_renderer',
            exhausted_target='target_renderer',
        ),
        {
            "then": 'identity_impact_router',
            "otherwise": 'target_renderer',
            "exhausted": 'target_renderer',
        },
    )
    workflow.add_conditional_edges(
        'identity_impact_router',
        create_state_condition_router(
            path='nodes.identity_impact_router.should_resolve_identity',
            operator='equals',
            expected=True,
            source='identity_impact_router',
            then_target='character_identity_resolver',
            otherwise_target='visual_impact_router',
            exhausted_target='visual_impact_router',
        ),
        {
            "then": 'character_identity_resolver',
            "otherwise": 'visual_impact_router',
            "exhausted": 'visual_impact_router',
        },
    )
    workflow.add_conditional_edges(
        'visual_impact_router',
        create_state_condition_router(
            path='nodes.visual_impact_router.should_resolve_visual',
            operator='equals',
            expected=True,
            source='visual_impact_router',
            then_target='visual_semantic_resolver',
            otherwise_target='prompt_compiler',
            exhausted_target='prompt_compiler',
        ),
        {
            "then": 'visual_semantic_resolver',
            "otherwise": 'prompt_compiler',
            "exhausted": 'prompt_compiler',
        },
    )
    workflow.add_conditional_edges(
        'consistency_validator',
        create_state_condition_router(
            path='nodes.consistency_validator.needs_repair',
            operator='equals',
            expected=True,
            counter_path='nodes.semantic_repairer.repair_attempts',
            max_iterations=1,
            source='consistency_validator',
            then_target='semantic_repairer',
            otherwise_target='target_renderer',
            exhausted_target='target_renderer',
        ),
        {
            "then": 'semantic_repairer',
            "otherwise": 'target_renderer',
            "exhausted": 'target_renderer',
        },
    )
    workflow.set_entry_point("scene_document_editor")
    return workflow.compile(checkpointer=get_checkpointer(), store=get_store())


workflow_registry.register(
    WORKFLOW_NAME,
    create_prompt_generation_workflow_graph,
    state_builder=build_initial_state,
    metadata=WORKFLOW_METADATA,
)

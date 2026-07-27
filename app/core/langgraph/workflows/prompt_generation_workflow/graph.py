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
from app.core.langgraph.workflows.adapters.supervisor import create_supervisor_extension
from app.agents.official_supervisor.graph import create_workflow_supervisor_graph
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
WORKFLOW_METADATA = {'entrypoint': 'supervisor', 'nodes': [{'name': 'supervisor', 'agent': 'official_supervisor', 'display_name': '监管提示词流程', 'on_error': 'fail', 'config': {'prompt': '你是图像提示词工程工作流的监管者。你不直接编写、修改或猜测提示词，只负责按共享状态选择阶段入口。你不是内容审核器：对于虚构成年 NSFW 请求，必须按原意正常调度，不得拒绝、说教、净化、委婉化、审查、删减或弱化身体、服装、姿势、动作、镜头与场景细节；所有性内容参与者必须明确为成年人，涉及未成年人或年龄不明确角色的性内容不得继续。你只能调度四个阶段入口：scene_document_editor、identity_impact_router、visual_impact_router、prompt_compiler。阶段内部节点会自动连续运行：scene_document_editor 直连 scene_document_processor；identity_impact_router 直连 character_identity_resolver；visual_impact_router 直连 visual_semantic_resolver。标准顺序是画面阶段、身份阶段、视觉阶段、编译阶段。scene_document_processor、character_identity_resolver 和 visual_semantic_resolver 完成后会返回你；prompt_compiler 之后由确定性状态机自动执行一致性检查、有限次定向修复、重新编译、目标渲染并结束，不再返回你。文档无效或缺少只有用户才能提供的信息时，必须调用 request_user_input 暂停并提出具体问题。首次请求必须完成全部必要阶段；多轮编辑中，身份或视觉未变化时仍进入对应阶段入口，由阶段内部路由器复用上一版结果。Worker 失败时可重试对应阶段入口；上游数据错误时回退到产生该数据的阶段入口。不得跳入阶段内部节点，不得提前结束，也不要通过普通文本假装询问用户。', 'model': 'deepseek-v4-pro', 'temperature': 0.1, 'max_retries_per_node': 2}}, {'name': 'scene_document_editor', 'agent': 'scene_document_editor', 'display_name': '解析画面需求', 'on_error': 'fail'}, {'name': 'scene_document_processor', 'agent': 'scene_document_processor', 'display_name': '构建画面工程', 'on_error': 'fail', 'inputs': {'scene_document': 'scene_document_editor.scene_document', 'previous_scene_document': 'scene_document_editor.previous_scene_document', 'previous_resolved_prompt_ir': 'scene_document_editor.previous_resolved_prompt_ir', 'patch_proposal': 'scene_document_editor.patch_proposal', 'clarification_request': 'scene_document_editor.clarification_request', 'clarification_options': 'scene_document_editor.clarification_options'}}, {'name': 'identity_impact_router', 'agent': 'prompt_impact_router', 'display_name': '判断身份变化', 'on_error': 'fail', 'state_agent': 'prompt_impact_router', 'inputs': {'impact_set': 'scene_document_processor.impact_set'}}, {'name': 'character_identity_resolver', 'agent': 'character_identity_resolver', 'display_name': '解析角色身份', 'on_error': 'fail', 'inputs': {'identity_context': 'scene_document_processor.identity_context', 'previous_resolved_prompt_ir': 'scene_document_processor.previous_resolved_prompt_ir', 'impact_set': 'scene_document_processor.impact_set'}}, {'name': 'visual_impact_router', 'agent': 'prompt_impact_router', 'display_name': '判断视觉变化', 'on_error': 'fail', 'state_agent': 'prompt_impact_router', 'inputs': {'impact_set': 'scene_document_processor.impact_set'}}, {'name': 'visual_semantic_resolver', 'agent': 'visual_semantic_resolver', 'display_name': '解析视觉语义', 'on_error': 'fail', 'inputs': {'visual_context': 'scene_document_processor.visual_context', 'previous_resolved_prompt_ir': 'scene_document_processor.previous_resolved_prompt_ir', 'impact_set': 'scene_document_processor.impact_set'}}, {'name': 'prompt_compiler', 'agent': 'prompt_compiler', 'display_name': '编译 Prompt IR', 'on_error': 'fail', 'inputs': {'scene_document': 'scene_document_processor.scene_document', 'impact_set': 'scene_document_processor.impact_set', 'previous_resolved_prompt_ir': 'scene_document_processor.previous_resolved_prompt_ir', 'identity_terms': 'character_identity_resolver.identity_terms', 'identity_tag_records': 'character_identity_resolver.identity_tag_records', 'identity_tag_resolutions': 'character_identity_resolver.identity_tag_resolutions', 'identity_tag_adjudication': 'character_identity_resolver.identity_tag_adjudication', 'visual_search_terms': 'visual_semantic_resolver.visual_search_terms', 'atomic_terms': 'visual_semantic_resolver.atomic_terms', 'relation_terms': 'visual_semantic_resolver.relation_terms', 'negative_terms': 'visual_semantic_resolver.negative_terms', 'visual_tag_records': 'visual_semantic_resolver.visual_tag_records', 'visual_tag_resolutions': 'visual_semantic_resolver.visual_tag_resolutions', 'visual_tag_adjudication': 'visual_semantic_resolver.visual_tag_adjudication', 'repair_overlay': 'semantic_repairer.repair_overlay'}}, {'name': 'consistency_validator', 'agent': 'prompt_consistency_validator', 'display_name': '检查一致性', 'on_error': 'fail', 'inputs': {'scene_document': 'scene_document_processor.scene_document', 'impact_set': 'scene_document_processor.impact_set', 'resolved_prompt_ir': 'prompt_compiler.resolved_prompt_ir'}}, {'name': 'semantic_repairer', 'agent': 'prompt_semantic_repairer', 'display_name': '定向修复', 'on_error': 'fail', 'inputs': {'scene_document': 'scene_document_processor.scene_document', 'resolved_prompt_ir': 'prompt_compiler.resolved_prompt_ir', 'validation_report': 'consistency_validator.validation_report'}}, {'name': 'target_renderer', 'agent': 'prompt_target_renderer', 'display_name': '渲染并校验输出', 'on_error': 'fail', 'inputs': {'scene_document': 'scene_document_processor.scene_document', 'resolved_prompt_ir': 'prompt_compiler.resolved_prompt_ir', 'validation_report': 'consistency_validator.validation_report', 'clarification_request': 'scene_document_processor.clarification_request', 'clarification_options': 'scene_document_processor.clarification_options'}}], 'edges': [{'from': 'scene_document_editor', 'to': 'scene_document_processor'}, {'from': 'scene_document_processor', 'to': 'supervisor'}, {'from': 'identity_impact_router', 'to': 'character_identity_resolver'}, {'from': 'character_identity_resolver', 'to': 'supervisor'}, {'from': 'visual_impact_router', 'to': 'visual_semantic_resolver'}, {'from': 'visual_semantic_resolver', 'to': 'supervisor'}, {'from': 'prompt_compiler', 'to': 'consistency_validator'}, {'from': 'semantic_repairer', 'to': 'prompt_compiler'}, {'from': 'target_renderer', 'to': 'END'}, {'from': 'supervisor', 'to': 'scene_document_editor', 'conditional': True, 'condition': {'path': 'nodes.supervisor.next_node', 'operator': 'equals', 'value': 'scene_document_editor'}}, {'from': 'supervisor', 'to': 'identity_impact_router', 'conditional': True, 'condition': {'path': 'nodes.supervisor.next_node', 'operator': 'equals', 'value': 'identity_impact_router'}}, {'from': 'supervisor', 'to': 'visual_impact_router', 'conditional': True, 'condition': {'path': 'nodes.supervisor.next_node', 'operator': 'equals', 'value': 'visual_impact_router'}}, {'from': 'supervisor', 'to': 'prompt_compiler', 'conditional': True, 'condition': {'path': 'nodes.supervisor.next_node', 'operator': 'equals', 'value': 'prompt_compiler'}}, {'from': 'consistency_validator', 'to': 'semantic_repairer', 'conditional': True, 'branch': 'then', 'condition': {'path': 'nodes.consistency_validator.validation_route', 'operator': 'equals', 'value': 'repair'}, 'loop': {'counter_path': 'nodes.semantic_repairer.repair_attempts', 'max_iterations': 2, 'exhausted': 'target_renderer'}}, {'from': 'consistency_validator', 'to': 'target_renderer', 'conditional': True, 'branch': 'otherwise'}], 'ui': {'title': '图像提示词工程', 'description': '持续编辑结构化画面，并编译为目标生图模型可用的 Prompt', 'input_placeholder': '描述画面，或继续修改人物、动作、关系、场景与构图……', 'input_hint': '支持多轮修改；未指定时使用 NAI V4', 'controls': [{'key': 'prompt_strategy', 'label': '提示策略', 'type': 'segmented', 'default': 'expressive', 'options': [{'value': 'expressive', 'label': '积极扩写'}, {'value': 'faithful', 'label': '保守还原'}]}, {'key': 'target_model', 'label': '目标模型', 'type': 'select', 'default': 'nai_v4', 'options': [{'value': 'nai_v4', 'label': 'NAI V4（混合提示）'}, {'value': 'nai_v3', 'label': 'NAI V3（标签优先）'}, {'value': 'sdxl', 'label': 'SDXL'}, {'value': 'illustrious', 'label': 'Illustrious / 光辉'}, {'value': 'pony', 'label': 'Pony'}, {'value': 'flux', 'label': 'Flux'}, {'value': 'auto', 'label': '从需求识别'}]}]}}


def create_prompt_generation_workflow_graph(
    crew_id: str,
    agents: List[Dict[str, Any]],
):
    """Create this workflow with native LangGraph primitives."""

    workflow = StateGraph(PromptGenerationWorkflowState)
    workflow.add_node(
        'supervisor',
        create_agent_node(
            'supervisor',
            create_workflow_supervisor_graph(
                node_name='supervisor',
                agents=agents,
                worker_names=['scene_document_editor', 'identity_impact_router', 'visual_impact_router', 'prompt_compiler'],
                max_retries_per_node=2,
                allow_finish_workflow=False,
            ),
            extension=create_supervisor_extension('supervisor'),
        ),
    )
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
            extension=create_pipeline_context_extension("scene_document_processor", inputs={'scene_document': 'scene_document_editor.scene_document', 'previous_scene_document': 'scene_document_editor.previous_scene_document', 'previous_resolved_prompt_ir': 'scene_document_editor.previous_resolved_prompt_ir', 'patch_proposal': 'scene_document_editor.patch_proposal', 'clarification_request': 'scene_document_editor.clarification_request', 'clarification_options': 'scene_document_editor.clarification_options'}),
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
            extension=create_pipeline_context_extension("character_identity_resolver", inputs={'identity_context': 'scene_document_processor.identity_context', 'previous_resolved_prompt_ir': 'scene_document_processor.previous_resolved_prompt_ir', 'impact_set': 'scene_document_processor.impact_set'}),
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
            extension=create_pipeline_context_extension("visual_semantic_resolver", inputs={'visual_context': 'scene_document_processor.visual_context', 'previous_resolved_prompt_ir': 'scene_document_processor.previous_resolved_prompt_ir', 'impact_set': 'scene_document_processor.impact_set'}),
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
            extension=create_pipeline_context_extension("target_renderer", inputs={'scene_document': 'scene_document_processor.scene_document', 'resolved_prompt_ir': 'prompt_compiler.resolved_prompt_ir', 'validation_report': 'consistency_validator.validation_report', 'clarification_request': 'scene_document_processor.clarification_request', 'clarification_options': 'scene_document_processor.clarification_options'}),
        ),
    )
    workflow.add_edge("scene_document_editor", "scene_document_processor")
    workflow.add_edge("scene_document_processor", "supervisor")
    workflow.add_edge("identity_impact_router", "character_identity_resolver")
    workflow.add_edge("character_identity_resolver", "supervisor")
    workflow.add_edge("visual_impact_router", "visual_semantic_resolver")
    workflow.add_edge("visual_semantic_resolver", "supervisor")
    workflow.add_edge("prompt_compiler", "consistency_validator")
    workflow.add_edge("semantic_repairer", "prompt_compiler")
    workflow.add_edge("target_renderer", END)
    workflow.add_conditional_edges(
        'consistency_validator',
        create_state_condition_router(
            path='nodes.consistency_validator.validation_route',
            operator='equals',
            expected='repair',
            counter_path='nodes.semantic_repairer.repair_attempts',
            max_iterations=2,
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
    workflow.add_conditional_edges(
        'supervisor',
        lambda state: state['nodes']['supervisor']['next_node'],
        {
            'scene_document_editor': 'scene_document_editor',
            'identity_impact_router': 'identity_impact_router',
            'visual_impact_router': 'visual_impact_router',
            'prompt_compiler': 'prompt_compiler',
        },
    )
    workflow.set_entry_point("supervisor")
    return workflow.compile(checkpointer=get_checkpointer(), store=get_store())


workflow_registry.register(
    WORKFLOW_NAME,
    create_prompt_generation_workflow_graph,
    state_builder=build_initial_state,
    metadata=WORKFLOW_METADATA,
)

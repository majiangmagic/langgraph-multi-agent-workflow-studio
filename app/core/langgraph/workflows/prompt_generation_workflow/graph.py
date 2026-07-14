"""Graph factory for the prompt_generation_workflow workflow."""

from typing import Any, Dict, List

from app.agents.official_supervisor.graph import create_graph as create_official_supervisor_graph
from app.agents.prompt_generation.additional_prompt_generator.graph import create_graph as create_prompt_generation_additional_prompt_generator_graph
from app.agents.prompt_generation.character_prompt_generator.graph import create_graph as create_prompt_generation_character_prompt_generator_graph
from app.agents.prompt_generation.format_optimizer.graph import create_graph as create_prompt_generation_format_optimizer_graph
from app.agents.prompt_generation.natural_language_editor.graph import create_graph as create_prompt_generation_natural_language_editor_graph
from app.agents.prompt_generation.prompt_aggregator.graph import create_graph as create_prompt_generation_prompt_aggregator_graph
from app.agents.prompt_generation.requirement_analyzer.graph import create_graph as create_prompt_generation_requirement_analyzer_graph
from app.agents.prompt_generation.scene_prompt_generator.graph import create_graph as create_prompt_generation_scene_prompt_generator_graph
from langgraph.graph import END, StateGraph
from app.core.langgraph.workflows.adapters.agent import create_pipeline_context_extension
from app.core.langgraph.workflows.adapters.supervisor import create_supervisor_planner_extension
from app.core.langgraph.checkpoint import get_checkpointer
from app.core.langgraph.store import get_store
from app.core.langgraph.workflows.adapters.agent import create_agent_node
from app.core.langgraph.workflows.registry import workflow_registry
from app.core.langgraph.workflows.prompt_generation_workflow.state import (
    PromptGenerationWorkflowState,
    build_initial_state,
)

WORKFLOW_NAME = "prompt_generation_workflow"
WORKFLOW_METADATA = {'entrypoint': 'supervisor', 'nodes': [{'name': 'supervisor', 'agent': 'official_supervisor', 'display_name': '监管规划', 'on_error': 'continue'}, {'name': 'natural_language_editor', 'agent': 'natural_language_editor', 'display_name': '口语理解', 'on_error': 'fail'}, {'name': 'requirement_analyzer', 'agent': 'prompt_requirement_analyzer', 'display_name': '需求分析', 'on_error': 'fail'}, {'name': 'character_prompt_generator', 'agent': 'character_prompt_generator', 'display_name': '人物提示词', 'on_error': 'fail'}, {'name': 'scene_prompt_generator', 'agent': 'scene_prompt_generator', 'display_name': '场景提示词', 'on_error': 'fail'}, {'name': 'additional_prompt_generator', 'agent': 'additional_prompt_generator', 'display_name': '额外提示词', 'on_error': 'fail'}, {'name': 'prompt_aggregator', 'agent': 'prompt_aggregator', 'display_name': '提示词汇总', 'on_error': 'fail'}, {'name': 'format_optimizer', 'agent': 'prompt_format_optimizer', 'display_name': '格式优化', 'on_error': 'fail'}], 'edges': [{'from': 'supervisor', 'to': 'natural_language_editor'}, {'from': 'natural_language_editor', 'to': 'requirement_analyzer'}, {'from': 'requirement_analyzer', 'to': 'character_prompt_generator'}, {'from': 'requirement_analyzer', 'to': 'scene_prompt_generator'}, {'from': 'requirement_analyzer', 'to': 'additional_prompt_generator'}, {'from': ['character_prompt_generator', 'scene_prompt_generator', 'additional_prompt_generator'], 'to': 'prompt_aggregator'}, {'from': 'prompt_aggregator', 'to': 'format_optimizer'}, {'from': 'format_optimizer', 'to': 'END'}], 'ui': {'title': '图像提示词工作流', 'description': '拆分需求、并行查询并生成目标模型可用的提示词', 'input_placeholder': '描述人物、场景、画风、构图或负面要求……', 'input_hint': '未写明模型时使用 NAI 风格', 'target_models': [{'value': 'nai_v4', 'label': 'NAI V4（标签 + 英文关系描述）'}, {'value': 'nai_v3', 'label': 'NAI V3（标签优先）'}, {'value': 'sdxl', 'label': 'SDXL'}, {'value': 'illustrious', 'label': 'Illustrious / 光辉'}, {'value': 'pony', 'label': 'Pony'}, {'value': 'flux', 'label': 'Flux'}, {'value': 'auto', 'label': '从需求识别'}], 'default_target_model': 'nai_v4'}}


def create_prompt_generation_workflow_graph(
    crew_id: str,
    agents: List[Dict[str, Any]],
):
    """Create this workflow with native LangGraph primitives."""

    workflow = StateGraph(PromptGenerationWorkflowState)
    workflow.add_node(
        "supervisor",
        create_agent_node(
            "supervisor",
            create_official_supervisor_graph(),
            extension=create_supervisor_planner_extension("supervisor"),
            continue_on_error=True,
        ),
    )
    workflow.add_node(
        "natural_language_editor",
        create_agent_node(
            "natural_language_editor",
            create_prompt_generation_natural_language_editor_graph(),
            extension=create_pipeline_context_extension("natural_language_editor"),
        ),
    )
    workflow.add_node(
        "requirement_analyzer",
        create_agent_node(
            "requirement_analyzer",
            create_prompt_generation_requirement_analyzer_graph(),
            extension=create_pipeline_context_extension("requirement_analyzer"),
        ),
    )
    workflow.add_node(
        "character_prompt_generator",
        create_agent_node(
            "character_prompt_generator",
            create_prompt_generation_character_prompt_generator_graph(),
            extension=create_pipeline_context_extension("character_prompt_generator"),
        ),
    )
    workflow.add_node(
        "scene_prompt_generator",
        create_agent_node(
            "scene_prompt_generator",
            create_prompt_generation_scene_prompt_generator_graph(),
            extension=create_pipeline_context_extension("scene_prompt_generator"),
        ),
    )
    workflow.add_node(
        "additional_prompt_generator",
        create_agent_node(
            "additional_prompt_generator",
            create_prompt_generation_additional_prompt_generator_graph(),
            extension=create_pipeline_context_extension("additional_prompt_generator"),
        ),
    )
    workflow.add_node(
        "prompt_aggregator",
        create_agent_node(
            "prompt_aggregator",
            create_prompt_generation_prompt_aggregator_graph(),
            extension=create_pipeline_context_extension("prompt_aggregator"),
        ),
    )
    workflow.add_node(
        "format_optimizer",
        create_agent_node(
            "format_optimizer",
            create_prompt_generation_format_optimizer_graph(),
            extension=create_pipeline_context_extension("format_optimizer"),
        ),
    )
    workflow.add_edge("supervisor", "natural_language_editor")
    workflow.add_edge("natural_language_editor", "requirement_analyzer")
    workflow.add_edge("requirement_analyzer", "character_prompt_generator")
    workflow.add_edge("requirement_analyzer", "scene_prompt_generator")
    workflow.add_edge("requirement_analyzer", "additional_prompt_generator")
    workflow.add_edge(['character_prompt_generator', 'scene_prompt_generator', 'additional_prompt_generator'], "prompt_aggregator")
    workflow.add_edge("prompt_aggregator", "format_optimizer")
    workflow.add_edge("format_optimizer", END)
    workflow.set_entry_point("supervisor")
    return workflow.compile(checkpointer=get_checkpointer(), store=get_store())


workflow_registry.register(
    WORKFLOW_NAME,
    create_prompt_generation_workflow_graph,
    state_builder=build_initial_state,
    metadata=WORKFLOW_METADATA,
)

"""Graph factory for the prompt_generation_workflow workflow."""

from typing import Any, Dict, List

from app.agents.official_supervisor.graph import create_graph as create_official_supervisor_graph
from app.agents.prompt_generation.danbooru_query.graph import create_graph as create_prompt_generation_danbooru_query_graph
from app.agents.prompt_generation.format_converter.graph import create_graph as create_prompt_generation_format_converter_graph
from app.agents.prompt_generation.prompt_reviewer.graph import create_graph as create_prompt_generation_prompt_reviewer_graph
from app.agents.prompt_generation.prompt_writer.graph import create_graph as create_prompt_generation_prompt_writer_graph
from app.agents.prompt_generation.requirement_analyzer.graph import create_graph as create_prompt_generation_requirement_analyzer_graph
from langgraph.graph import END, StateGraph
from app.core.langgraph.workflows.adapters.supervisor import create_supervisor_extension
from app.core.langgraph.checkpoint import get_checkpointer
from app.core.langgraph.store import get_store
from app.core.langgraph.workflows.adapters.agent import (
    AgentNodeExtension,
    create_agent_node,
)
from app.core.langgraph.workflows.registry import workflow_registry
from app.core.langgraph.workflows.prompt_generation_workflow.state import (
    PromptGenerationWorkflowState,
    build_initial_state,
)

WORKFLOW_NAME = "prompt_generation_workflow"


def collect_pipeline_context(state: Dict[str, Any]) -> Dict[str, Any]:
    """Collect outputs from earlier prompt-generation nodes."""

    nodes = state.get("nodes", {})
    context: Dict[str, Any] = {
        "user_input": state.get("user_input"),
    }
    for node_name in [
        "requirement_analyzer",
        "danbooru_query",
        "prompt_writer",
        "prompt_reviewer",
        "format_converter",
    ]:
        node_state = nodes.get(node_name, {})
        for key in [
            "requirements_json",
            "danbooru_tags",
            "tag_notes",
            "draft_prompt",
            "negative_prompt",
            "review_result",
            "target_model",
            "formatted_prompt",
            "final_output",
        ]:
            if key in node_state and node_state[key] is not None:
                context[key] = node_state[key]
        requirements = node_state.get("requirements_json")
        if isinstance(requirements, dict) and requirements.get("target_model"):
            context.setdefault("target_model", requirements["target_model"])
    return context


def create_prompt_pipeline_extension(node_name: str) -> AgentNodeExtension:
    """Let prompt pipeline nodes read upstream node outputs."""

    def prepare_agent_state(state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            **state["nodes"][node_name],
            **collect_pipeline_context(state),
        }

    def build_workflow_update(
        state: Dict[str, Any],
        updated_agent_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {"nodes": {node_name: updated_agent_state}}

    return AgentNodeExtension(
        prepare_agent_state=prepare_agent_state,
        build_workflow_update=build_workflow_update,
    )


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
            extension=create_supervisor_extension("supervisor"),
        ),
    )
    workflow.add_node(
        "requirement_analyzer",
        create_agent_node(
            "requirement_analyzer",
            create_prompt_generation_requirement_analyzer_graph(),
            extension=create_prompt_pipeline_extension("requirement_analyzer"),
        ),
    )
    workflow.add_node(
        "danbooru_query",
        create_agent_node(
            "danbooru_query",
            create_prompt_generation_danbooru_query_graph(),
            extension=create_prompt_pipeline_extension("danbooru_query"),
        ),
    )
    workflow.add_node(
        "prompt_writer",
        create_agent_node(
            "prompt_writer",
            create_prompt_generation_prompt_writer_graph(),
            extension=create_prompt_pipeline_extension("prompt_writer"),
        ),
    )
    workflow.add_node(
        "prompt_reviewer",
        create_agent_node(
            "prompt_reviewer",
            create_prompt_generation_prompt_reviewer_graph(),
            extension=create_prompt_pipeline_extension("prompt_reviewer"),
        ),
    )
    workflow.add_node(
        "format_converter",
        create_agent_node(
            "format_converter",
            create_prompt_generation_format_converter_graph(),
            extension=create_prompt_pipeline_extension("format_converter"),
        ),
    )
    workflow.add_edge("supervisor", "requirement_analyzer")
    workflow.add_edge("requirement_analyzer", "danbooru_query")
    workflow.add_edge("danbooru_query", "prompt_writer")
    workflow.add_edge("prompt_writer", "prompt_reviewer")
    workflow.add_edge("prompt_reviewer", "format_converter")
    workflow.add_edge("format_converter", END)
    workflow.set_entry_point("supervisor")
    return workflow.compile(checkpointer=get_checkpointer(), store=get_store())


workflow_registry.register(
    WORKFLOW_NAME,
    create_prompt_generation_workflow_graph,
    state_builder=build_initial_state,
)

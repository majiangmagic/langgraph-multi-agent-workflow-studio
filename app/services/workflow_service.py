"""Service helpers for selecting and creating LangGraph workflows."""

import logging
from typing import Any, Dict, List, Tuple

from app.core.langgraph.workflows.prompt_generation_workflow import (  # noqa: F401
    create_prompt_generation_workflow_graph,
)
from app.core.langgraph.workflows.registry import workflow_registry
from app.core.langgraph.workflows.supervisor_simple import (  # noqa: F401
    create_supervisor_simple_graph,
)
from app.models.crew import Crew

logger = logging.getLogger(__name__)

DEFAULT_WORKFLOW_TYPE = "supervisor_simple"


class WorkflowService:
    """Selects workflow implementations from crew configuration."""

    @staticmethod
    def get_workflow_type(crew: Crew) -> str:
        """Read workflow type from crew settings, falling back to supervisor."""

        settings = crew.settings or {}
        return settings.get("workflow_type") or DEFAULT_WORKFLOW_TYPE

    @staticmethod
    def create_workflow(
        crew: Crew,
        agents: List[Dict[str, Any]],
    ):
        """Create the configured workflow for a crew.

        Unknown workflow types are logged and fall back to the supervisor workflow.
        """

        workflow_type = WorkflowService.get_workflow_type(crew)
        if workflow_type not in workflow_registry.names():
            logger.warning(
                "Unsupported workflow_type '%s' for crew %s; falling back to '%s'",
                workflow_type,
                crew.id,
                DEFAULT_WORKFLOW_TYPE,
            )

        workflow_factory = workflow_registry.get(workflow_type, fallback=True)
        return workflow_factory(
            crew_id=str(crew.id),
            agents=agents,
        )

    @staticmethod
    def build_initial_state(
        crew: Crew,
        agents: List[Dict[str, Any]],
        conversation_id: str,
        user_id: str,
        user_input: str,
    ) -> Dict[str, Any]:
        """Build the configured workflow's initial state from common context."""

        workflow_type = WorkflowService.get_workflow_type(crew)
        state_builder = workflow_registry.get_state_builder(workflow_type, fallback=True)
        if state_builder is None:
            raise ValueError(f"Workflow '{workflow_type}' has no state builder")

        return state_builder(
            crew_id=str(crew.id),
            agents=agents,
            user_id=user_id,
            conversation_id=conversation_id,
            user_input=user_input,
        )

    @staticmethod
    def create_workflow_run(
        crew: Crew,
        agents: List[Dict[str, Any]],
        conversation_id: str,
        user_id: str,
        user_input: str,
    ) -> Tuple[Any, Dict[str, Any]]:
        """Create a workflow and its initial state without exposing state shape."""

        workflow = WorkflowService.create_workflow(
            crew=crew,
            agents=agents,
        )
        initial_state = WorkflowService.build_initial_state(
            crew=crew,
            agents=agents,
            conversation_id=conversation_id,
            user_id=user_id,
            user_input=user_input,
        )
        return workflow, initial_state

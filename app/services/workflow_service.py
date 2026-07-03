"""Service helpers for selecting and creating LangGraph workflows."""

import logging
from typing import Any, Dict, List, Optional

from app.core.langgraph.workflows.registry import workflow_registry
from app.core.langgraph.workflows.orchestrated import create_orchestrated_graph  # noqa: F401
from app.models.crew import Crew

logger = logging.getLogger(__name__)

DEFAULT_WORKFLOW_TYPE = "orchestrated"


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
        system_prompt: Optional[str] = None,
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
            system_prompt=system_prompt,
        )

"""Select registered workflows and bind their local Agent manifests."""

import importlib
import logging
import pkgutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import BaseMessage

import app.core.langgraph.workflows as workflows_package
from app.agents.catalog import resolve_workflow_agent_configs
from app.core.langgraph.workflows.registry import workflow_registry
from app.models.crew import Crew


logger = logging.getLogger(__name__)
DEFAULT_WORKFLOW_TYPE = "supervisor_simple"


def discover_local_workflows() -> None:
    """Import every local workflow graph so its registry hook runs."""

    workflows_dir = Path(next(iter(workflows_package.__path__)))
    for module in pkgutil.iter_modules(workflows_package.__path__):
        if not module.ispkg or module.name.startswith("_"):
            continue
        if not (workflows_dir / module.name / "graph.py").is_file():
            continue
        try:
            importlib.import_module(
                f"{workflows_package.__name__}.{module.name}.graph"
            )
        except ModuleNotFoundError as exc:
            logger.warning("Skipped local workflow '%s': %s", module.name, exc)


discover_local_workflows()


class WorkflowService:
    """Build workflows from local definitions; Crew stores only the selection."""

    @staticmethod
    def get_workflow_type(crew: Crew) -> str:
        return crew.workflow_type or DEFAULT_WORKFLOW_TYPE

    @staticmethod
    def require_workflow(crew: Crew) -> str:
        workflow_type = WorkflowService.get_workflow_type(crew)
        if workflow_type not in workflow_registry.names():
            raise ValueError(
                f"Crew '{crew.id}' references missing workflow '{workflow_type}'"
            )
        return workflow_type

    @staticmethod
    def local_agent_configs(crew: Crew) -> List[Dict[str, Any]]:
        workflow_type = WorkflowService.require_workflow(crew)
        metadata = workflow_registry.get_metadata(workflow_type, fallback=False)
        return resolve_workflow_agent_configs(metadata)

    @staticmethod
    def create_workflow(crew: Crew):
        workflow_type = WorkflowService.require_workflow(crew)
        local_agents = WorkflowService.local_agent_configs(crew)
        return workflow_registry.get(workflow_type, fallback=False)(
            crew_id=str(crew.id), agents=local_agents
        )

    @staticmethod
    def build_initial_state(
        crew: Crew,
        conversation_id: str,
        user_id: str,
        user_input: str,
        messages: Optional[List[BaseMessage]] = None,
        workflow_inputs: Optional[Dict[str, Any]] = None,
        request_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build state exclusively from local Agent manifests."""

        workflow_type = WorkflowService.require_workflow(crew)
        state_builder = workflow_registry.get_state_builder(
            workflow_type, fallback=False
        )
        if state_builder is None:
            raise ValueError(f"Workflow '{workflow_type}' has no state builder")
        return state_builder(
            crew_id=str(crew.id),
            agents=WorkflowService.local_agent_configs(crew),
            user_id=user_id,
            conversation_id=conversation_id,
            messages=messages,
            user_input=user_input,
            workflow_inputs=workflow_inputs,
            request_context=request_context,
        )

    @staticmethod
    def create_workflow_run(
        crew: Crew,
        conversation_id: str,
        user_id: str,
        user_input: str,
        messages: Optional[List[BaseMessage]] = None,
        workflow_inputs: Optional[Dict[str, Any]] = None,
        request_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, Dict[str, Any]]:
        workflow = WorkflowService.create_workflow(crew)
        state = WorkflowService.build_initial_state(
            crew=crew,
            conversation_id=conversation_id,
            user_id=user_id,
            user_input=user_input,
            messages=messages,
            workflow_inputs=workflow_inputs,
            request_context=request_context,
        )
        return workflow, state

"""API routes for workflow discovery."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.langgraph.workflows.registry import workflow_registry
from app.db.base import get_db
from app.schemas.crew import AgentCreate, CrewCreate, CrewResponse
from app.services import workflow_service as _workflow_service  # noqa: F401
from app.services.crew_service import AgentService, CrewService
from app.services.workflow_service import DEFAULT_WORKFLOW_TYPE


router = APIRouter(prefix="/workflows", tags=["workflows"])


class WorkflowOption(BaseModel):
    """Public workflow option used by the lightweight web UI."""

    name: str
    is_default: bool = False


@router.get("/", response_model=List[WorkflowOption])
async def get_workflows():
    """List workflow types registered in the backend."""

    return [
        WorkflowOption(name=name, is_default=name == DEFAULT_WORKFLOW_TYPE)
        for name in workflow_registry.names()
    ]


def sample_agents_for_workflow(workflow_name: str) -> list[dict]:
    """Return minimal agent configs needed by a workflow."""

    if workflow_name == "supervisor_simple":
        return [
            {
                "name": "supervisor",
                "description": "Default supervisor agent.",
                "system_prompt": "You coordinate the crew and answer clearly.",
                "is_supervisor": True,
                "temperature": 0.2,
            }
        ]

    if workflow_name == "prompt_generation_workflow":
        return [
            {
                "name": "official_supervisor",
                "description": "Coordinates the prompt generation pipeline.",
                "system_prompt": "Coordinate the prompt generation agents.",
                "is_supervisor": True,
                "temperature": 0.2,
            },
            {
                "name": "prompt_requirement_analyzer",
                "description": "Extracts structured image prompt requirements.",
                "system_prompt": "Analyze image prompt requirements as structured JSON.",
                "is_supervisor": False,
                "temperature": 0.2,
            },
            {
                "name": "prompt_danbooru_query",
                "description": "Maps requirements to Danbooru-style tags.",
                "system_prompt": "Map image requirements to useful Danbooru tags.",
                "is_supervisor": False,
                "temperature": 0.2,
            },
            {
                "name": "prompt_writer",
                "description": "Writes image generation prompt drafts.",
                "system_prompt": "Write clear image generation prompts.",
                "is_supervisor": False,
                "temperature": 0.4,
            },
            {
                "name": "prompt_reviewer",
                "description": "Reviews prompt clarity and usefulness.",
                "system_prompt": "Review prompts for clarity and model usefulness.",
                "is_supervisor": False,
                "temperature": 0.2,
            },
            {
                "name": "prompt_format_converter",
                "description": "Converts prompts for target image models.",
                "system_prompt": "Convert prompts into model-specific formats.",
                "is_supervisor": False,
                "temperature": 0.2,
            },
        ]

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Unknown workflow '{workflow_name}'",
    )


@router.post("/{workflow_name}/sample-crew", response_model=CrewResponse)
async def create_sample_crew(
    workflow_name: str,
    db: AsyncSession = Depends(get_db),
):
    """Create a minimal crew with agents for a workflow."""

    if workflow_name not in workflow_registry.names():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown workflow '{workflow_name}'",
        )

    crew = await CrewService.create_crew(
        db,
        CrewCreate(
            name=f"{workflow_name} demo",
            description=f"Demo crew for {workflow_name}",
            settings={"workflow_type": workflow_name},
        ),
    )
    await db.flush()

    for agent_data in sample_agents_for_workflow(workflow_name):
        await AgentService.create_agent(
            db,
            AgentCreate(
                crew_id=crew.id,
                **agent_data,
            ),
        )

    await db.commit()
    await db.refresh(crew)
    return crew

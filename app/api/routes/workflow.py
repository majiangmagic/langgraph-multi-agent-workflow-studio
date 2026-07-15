"""API routes for workflow discovery."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.langgraph.workflows.registry import workflow_registry
from app.db.base import get_db
from app.schemas.crew import CrewCreate, CrewResponse
from app.services import workflow_service as _workflow_service  # noqa: F401
from app.services.crew_service import CrewService
from app.services.workflow_service import DEFAULT_WORKFLOW_TYPE


router = APIRouter(prefix="/workflows", tags=["workflows"])


class WorkflowOption(BaseModel):
    """Public workflow option used by the lightweight web UI."""

    name: str
    is_default: bool = False
    entrypoint: str | None = None
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    edges: List[Dict[str, Any]] = Field(default_factory=list)
    ui: Dict[str, Any] = Field(default_factory=dict)


@router.get("/", response_model=List[WorkflowOption])
async def get_workflows():
    """List workflow types registered in the backend."""

    options = []
    for name in workflow_registry.names():
        metadata = workflow_registry.get_metadata(name, fallback=False)
        options.append(
            WorkflowOption(
                name=name,
                is_default=name == DEFAULT_WORKFLOW_TYPE,
                entrypoint=metadata.get("entrypoint"),
                nodes=metadata.get("nodes") or [],
                edges=metadata.get("edges") or [],
                ui=metadata.get("ui") or {},
            )
        )
    return options


@router.post("/{workflow_name}/sample-crew", response_model=CrewResponse)
async def create_sample_crew(
    workflow_name: str,
    db: AsyncSession = Depends(get_db),
):
    """Create a Crew that stores only its selected local workflow name."""

    if workflow_name not in workflow_registry.names():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown workflow '{workflow_name}'",
        )

    existing_crews = await CrewService.get_crews(db)
    workflow_crew_count = sum(
        1
        for crew in existing_crews
        if crew.workflow_type == workflow_name
    )
    crew_name = f"{workflow_name} demo {workflow_crew_count + 1}"

    crew = await CrewService.create_crew(
        db,
        CrewCreate(
            name=crew_name,
            description=f"Demo crew for {workflow_name}",
            workflow_type=workflow_name,
        ),
    )
    await db.flush()

    await db.commit()
    await db.refresh(crew)
    return crew

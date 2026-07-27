"""API routes for workflow discovery."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.workflows.registry import workflow_registry
from app.infrastructure.database.session import get_db
from app.api.schemas.crew import CrewCreate, CrewResponse
from app.application import workflow_service as _workflow_service  # noqa: F401
from app.application.crew_service import CrewService
from app.application.workflow_export_service import export_workflow
from app.application.workflow_service import DEFAULT_WORKFLOW_TYPE


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


@router.get("/{workflow_name}/export")
async def download_workflow_export(workflow_name: str, request: Request):
    """Download a database-free standalone LangGraph workflow package."""

    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workflow source export is a local-only operation",
        )
    try:
        artifact = export_workflow(workflow_name)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown workflow '{workflow_name}'",
        )
    except (OSError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    return Response(
        content=artifact.content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{artifact.filename}"',
            "X-Exported-File-Count": str(artifact.file_count),
        },
    )


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

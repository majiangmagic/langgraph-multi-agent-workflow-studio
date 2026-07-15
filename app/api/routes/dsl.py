"""Local Agent and Workflow DSL design endpoints."""

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.dsl_service import (
    generate_dsl,
    list_dsls,
    read_dsl,
    save_dsl,
    validate_dsl,
)


DslKind = Literal["agent", "workflow"]
router = APIRouter(prefix="/dsl", tags=["dsl"])


class DslDocument(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)


def bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


def require_local_request(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(
            status_code=403,
            detail="DSL persistence and code generation are local-only operations",
        )


@router.get("/{kind}")
async def get_dsl_list(kind: DslKind):
    return list_dsls(kind)


@router.get("/{kind}/{name}")
async def get_dsl(kind: DslKind, name: str):
    try:
        return {"kind": kind, "name": name, "data": read_dsl(kind, name)}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"DSL '{name}' not found")
    except (ValueError, OSError) as exc:
        raise bad_request(exc)


@router.post("/{kind}/validate")
async def validate_dsl_document(kind: DslKind, document: DslDocument):
    try:
        return validate_dsl(kind, document.data)
    except (KeyError, TypeError, ValueError) as exc:
        raise bad_request(exc)


@router.put("/{kind}/{name}")
async def put_dsl(
    kind: DslKind,
    name: str,
    document: DslDocument,
    request: Request,
):
    require_local_request(request)
    try:
        return save_dsl(kind, name, document.data)
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise bad_request(exc)


@router.post("/{kind}/{name}/generate")
async def generate_dsl_code(
    kind: DslKind,
    name: str,
    document: DslDocument,
    request: Request,
):
    require_local_request(request)
    try:
        if document.data.get("name") != name:
            raise ValueError("URL name must match data.name")
        save_dsl(kind, name, document.data)
        return generate_dsl(kind, document.data)
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise bad_request(exc)

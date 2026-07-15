"""Pydantic schemas for Crews and MCP connections."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field


class CrewStatusEnum(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    MAINTENANCE = "maintenance"


class CrewBase(BaseModel):
    name: str
    description: Optional[str] = None
    status: CrewStatusEnum = CrewStatusEnum.ACTIVE
    workflow_type: str = "supervisor_simple"
    settings: Dict[str, Any] = Field(default_factory=dict)


class MCPServerBase(BaseModel):
    name: str
    description: Optional[str] = None
    url: str
    settings: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class CrewCreate(CrewBase):
    pass


class MCPServerCreate(MCPServerBase):
    pass


class CrewResponse(CrewBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def workflow_missing(self) -> bool:
        from app.core.langgraph.workflows.registry import workflow_registry

        return self.workflow_type not in workflow_registry.names()

    model_config = ConfigDict(from_attributes=True)


class MCPServerResponse(MCPServerBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MCPToolBase(BaseModel):
    name: str
    description: Optional[str] = None
    parameters_schema: Dict[str, Any] = Field(default_factory=dict)


class MCPToolResponse(MCPToolBase):
    id: UUID
    mcp_server_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CrewWithServers(CrewResponse):
    mcp_servers: List[MCPServerResponse] = Field(default_factory=list)


class CrewUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[CrewStatusEnum] = None
    workflow_type: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


class MCPServerUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

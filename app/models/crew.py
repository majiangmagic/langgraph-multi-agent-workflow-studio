"""
Database models for AI crews and related entities
"""
import enum
import uuid
from datetime import datetime
from typing import List
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, JSON, Enum, Table
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, relationship, mapped_column

from app.core.config import settings
from app.db.base import Base


# Association table for crews and MCP servers
table_kwargs = {"schema": settings.database_schema} if settings.database_schema else {}
crew_mcp_association = Table(
    "crew_mcp_servers",
    Base.metadata,
    Column("crew_id", UUID(as_uuid=True), ForeignKey("crews.id", ondelete="CASCADE"), primary_key=True),
    Column("mcp_server_id", UUID(as_uuid=True), ForeignKey("mcp_servers.id", ondelete="CASCADE"), primary_key=True),
    **table_kwargs,
)


class CrewStatus(enum.Enum):
    """Status of an AI crew"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    MAINTENANCE = "maintenance"


class Crew(Base):
    """A user workspace bound to one locally defined Workflow."""
    __tablename__ = "crews"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=Base.generate_uuid
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[CrewStatus] = mapped_column(
        Enum(CrewStatus, values_callable=lambda enum_cls: [item.value for item in enum_cls]),
        default=CrewStatus.ACTIVE,
        nullable=False,
    )
    workflow_type: Mapped[str] = mapped_column(
        String(255), default="supervisor_simple", nullable=False, index=True
    )
    settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    
    # Relationships
    # Many-to-many relationship with MCP servers
    mcp_servers = relationship(
        "MCPServer",
        secondary=crew_mcp_association,
        back_populates="crews"
    )
    
    # Conversations
    conversations: Mapped[List["Conversation"]] = relationship(
        "Conversation", back_populates="crew", cascade="all, delete-orphan"
    )

class MCPServer(Base):
    """MCP Server model - provides tools via MCP protocol"""
    __tablename__ = "mcp_servers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=Base.generate_uuid
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships - many-to-many with crews
    crews = relationship(
        "Crew",
        secondary=crew_mcp_association,
        back_populates="mcp_servers"
    )
    
    # Available tools in this MCP server
    tools: Mapped[List["MCPTool"]] = relationship(
        "MCPTool", back_populates="mcp_server", cascade="all, delete-orphan"
    )


class MCPTool(Base):
    """Model for tools available in an MCP server"""
    __tablename__ = "mcp_tools"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=Base.generate_uuid
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    parameters_schema: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    
    # Foreign keys
    mcp_server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mcp_servers.id", ondelete="CASCADE"), nullable=False
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    
    # Relationships
    mcp_server: Mapped["MCPServer"] = relationship("MCPServer", back_populates="tools")

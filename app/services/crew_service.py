"""Database services for Crews and MCP connections."""

from typing import List, Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.crew import Crew, MCPServer, MCPTool
from app.schemas.crew import CrewCreate, CrewUpdate


class CrewService:
    @staticmethod
    async def get_crews(
        db: AsyncSession, skip: int = 0, limit: int = 100
    ) -> List[Crew]:
        result = await db.execute(select(Crew).offset(skip).limit(limit))
        return list(result.scalars().all())

    @staticmethod
    async def get_crew(db: AsyncSession, crew_id: uuid.UUID) -> Optional[Crew]:
        result = await db.execute(
            select(Crew)
            .where(Crew.id == crew_id)
            .options(selectinload(Crew.mcp_servers))
        )
        return result.scalars().first()

    @staticmethod
    async def create_crew(db: AsyncSession, crew_data: CrewCreate) -> Crew:
        crew = Crew(**crew_data.model_dump())
        db.add(crew)
        await db.flush()
        return crew

    @staticmethod
    async def update_crew(
        db: AsyncSession, crew_id: uuid.UUID, crew_data: CrewUpdate
    ) -> Optional[Crew]:
        crew = await CrewService.get_crew(db, crew_id)
        if not crew:
            return None
        for key, value in crew_data.model_dump(exclude_unset=True).items():
            setattr(crew, key, value)
        await db.flush()
        return crew

    @staticmethod
    async def delete_crew(db: AsyncSession, crew_id: uuid.UUID) -> bool:
        crew = await CrewService.get_crew(db, crew_id)
        if not crew:
            return False
        await db.delete(crew)
        await db.flush()
        return True

    @staticmethod
    async def add_mcp_server_to_crew(
        db: AsyncSession, crew_id: uuid.UUID, server_id: uuid.UUID
    ) -> bool:
        crew = await CrewService.get_crew(db, crew_id)
        server = await MCPServerService.get_server(db, server_id)
        if not crew or not server:
            return False
        crew.mcp_servers.append(server)
        await db.flush()
        return True

    @staticmethod
    async def remove_mcp_server_from_crew(
        db: AsyncSession, crew_id: uuid.UUID, server_id: uuid.UUID
    ) -> bool:
        crew = await CrewService.get_crew(db, crew_id)
        server = await MCPServerService.get_server(db, server_id)
        if not crew or not server or server not in crew.mcp_servers:
            return False
        crew.mcp_servers.remove(server)
        await db.flush()
        return True


class MCPServerService:
    @staticmethod
    async def get_servers(
        db: AsyncSession, skip: int = 0, limit: int = 100
    ) -> List[MCPServer]:
        result = await db.execute(select(MCPServer).offset(skip).limit(limit))
        return list(result.scalars().all())

    @staticmethod
    async def get_server(
        db: AsyncSession, server_id: uuid.UUID
    ) -> Optional[MCPServer]:
        result = await db.execute(select(MCPServer).where(MCPServer.id == server_id))
        return result.scalars().first()

    @staticmethod
    async def get_server_by_url(
        db: AsyncSession, url: str
    ) -> Optional[MCPServer]:
        result = await db.execute(select(MCPServer).where(MCPServer.url == url))
        return result.scalars().first()

    @staticmethod
    async def create_server(db: AsyncSession, server_data: dict) -> MCPServer:
        server = MCPServer(**server_data)
        db.add(server)
        await db.flush()
        return server

    @staticmethod
    async def update_server(
        db: AsyncSession, server_id: uuid.UUID, server_data: dict
    ) -> Optional[MCPServer]:
        server = await MCPServerService.get_server(db, server_id)
        if not server:
            return None
        for key, value in server_data.items():
            setattr(server, key, value)
        await db.flush()
        return server

    @staticmethod
    async def delete_server(db: AsyncSession, server_id: uuid.UUID) -> bool:
        server = await MCPServerService.get_server(db, server_id)
        if not server:
            return False
        await db.delete(server)
        await db.flush()
        return True

    @staticmethod
    async def get_tools(db: AsyncSession, server_id: uuid.UUID) -> List[MCPTool]:
        result = await db.execute(
            select(MCPTool).where(MCPTool.mcp_server_id == server_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_tool(db: AsyncSession, tool_id: uuid.UUID) -> Optional[MCPTool]:
        result = await db.execute(select(MCPTool).where(MCPTool.id == tool_id))
        return result.scalars().first()

    @staticmethod
    async def create_tool(db: AsyncSession, tool_data: dict) -> MCPTool:
        tool = MCPTool(**tool_data)
        db.add(tool)
        await db.flush()
        return tool

    @staticmethod
    async def update_tool(
        db: AsyncSession, tool_id: uuid.UUID, tool_data: dict
    ) -> Optional[MCPTool]:
        tool = await MCPServerService.get_tool(db, tool_id)
        if not tool:
            return None
        for key, value in tool_data.items():
            setattr(tool, key, value)
        await db.flush()
        return tool

    @staticmethod
    async def delete_tool(db: AsyncSession, tool_id: uuid.UUID) -> bool:
        tool = await MCPServerService.get_tool(db, tool_id)
        if not tool:
            return False
        await db.delete(tool)
        await db.flush()
        return True

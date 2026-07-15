"""
API routes for Crew management
"""
from typing import List
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.services.crew_service import CrewService
from app.schemas.crew import (
    CrewCreate, 
    CrewUpdate, 
    CrewResponse, 
    CrewWithServers,
)


router = APIRouter()

# Crew routes
crews_router = APIRouter(prefix="/crews", tags=["crews"])

@crews_router.get("/", response_model=List[CrewResponse])
async def get_crews(
    skip: int = 0, 
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Get a list of all crews"""
    crews = await CrewService.get_crews(db, skip=skip, limit=limit)
    return crews


@crews_router.post("/", response_model=CrewResponse, status_code=status.HTTP_201_CREATED)
async def create_crew(
    crew: CrewCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new crew"""
    db_crew = await CrewService.create_crew(db, crew)
    return db_crew


@crews_router.get("/{crew_id}", response_model=CrewWithServers)
async def get_crew(
    crew_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific crew by ID"""
    crew = await CrewService.get_crew(db, crew_id)
    if not crew:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crew with ID {crew_id} not found"
        )
    return crew


@crews_router.put("/{crew_id}", response_model=CrewResponse)
async def update_crew(
    crew_id: uuid.UUID,
    crew_update: CrewUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a crew"""
    updated_crew = await CrewService.update_crew(db, crew_id, crew_update)
    if not updated_crew:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crew with ID {crew_id} not found"
        )
    return updated_crew


@crews_router.delete("/{crew_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_crew(
    crew_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete a crew"""
    success = await CrewService.delete_crew(db, crew_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crew with ID {crew_id} not found"
        )
    return None


# Add Crew routes to main router
router.include_router(crews_router)

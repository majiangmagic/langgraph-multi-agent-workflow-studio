"""Storage API response schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FileResponse(BaseModel):
    key: str
    filename: str
    content_type: str | None = None
    size: int = 0
    url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    last_modified: datetime | str | None = None


class PresignedUrlResponse(BaseModel):
    url: str
    expires_in: int

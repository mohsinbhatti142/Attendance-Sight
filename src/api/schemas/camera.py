"""Pydantic schemas for Camera endpoints."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CameraBase(BaseModel):
    """Base schema for Camera data."""
    name: str = Field(..., min_length=1, max_length=100, description="Camera name")
    source: str = Field(..., min_length=1, max_length=500, description="RTSP URL or camera index")
    camera_type: str = Field(default="BOTH", description="ENTRY, EXIT, or BOTH")
    location: Optional[str] = Field(None, max_length=200, description="Physical location")


class CameraCreate(CameraBase):
    """Schema for creating a new camera."""
    pass


class CameraResponse(CameraBase):
    """Schema for camera response."""
    id: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CameraStatus(BaseModel):
    """Schema for real-time camera status."""
    id: int
    name: str
    is_active: bool
    is_connected: bool
    fps: Optional[float] = None
    resolution: Optional[str] = None

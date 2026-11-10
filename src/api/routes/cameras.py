"""Camera management API routes."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_db
from src.db.models import Camera
from src.api.schemas.camera import CameraCreate, CameraResponse, CameraStatus
from src.utils.logger import logger
from src.api.deps import require_admin

router = APIRouter(prefix="/cameras", tags=["Cameras"], dependencies=[Depends(require_admin)])


@router.get("/", response_model=list[CameraResponse])
async def list_cameras(db: AsyncSession = Depends(get_db)):
    """List all registered cameras."""
    result = await db.execute(select(Camera).order_by(Camera.name))
    cameras = result.scalars().all()
    return [CameraResponse.model_validate(c) for c in cameras]


@router.post("/", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
async def add_camera(
    camera: CameraCreate,
    db: AsyncSession = Depends(get_db),
):
    """Register a new camera source (webcam, RTSP, etc.)."""
    db_camera = Camera(**camera.model_dump())
    db.add(db_camera)
    await db.flush()
    await db.refresh(db_camera)
    
    logger.info(f"Camera registered: {db_camera.name} ({db_camera.source})")
    return CameraResponse.model_validate(db_camera)

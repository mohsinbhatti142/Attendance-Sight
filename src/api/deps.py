"""API Dependencies for dependency injection."""
from typing import AsyncGenerator
from fastapi import Depends, HTTPException, Request, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_db
from src.services.face_detection import face_detector, FaceDetectionService
from src.services.face_matching import face_matcher, FaceMatchingService
from src.services.attendance import attendance_service, AttendanceService
from src.core.security import verify_token
from src.db.models import AdminUser


async def get_database(db: AsyncSession = Depends(get_db)) -> AsyncGenerator[AsyncSession, None]:
    """Get database session dependency."""
    yield db


def get_face_detector() -> FaceDetectionService:
    """Get face detection service."""
    return face_detector


def get_face_matcher() -> FaceMatchingService:
    """Get face matching service."""
    return face_matcher


def get_attendance_service() -> AttendanceService:
    """Get attendance service."""
    return attendance_service


async def require_admin(request: Request, db: AsyncSession = Depends(get_db)) -> AdminUser:
    """Validate the signed browser session and return its active admin account."""
    token = request.cookies.get("attendsight_session")
    if not token:
        header = request.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            token = header[7:]
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        payload = verify_token(token)
        user_id = int(payload.get("sub", 0))
    except (JWTError, TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
    user = await db.get(AdminUser, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin account is inactive")
    if payload.get("ver", 0) != user.session_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has been revoked")
    return user


def require_ai_ready(request: Request) -> None:
    """Reject AI operations until model and matcher initialization has completed."""
    ai_status = getattr(request.app.state, "ai_status", "starting")
    if ai_status == "loading":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI services are still initializing. Please try again shortly.",
        )
    if ai_status != "ready":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI services are unavailable. Check the server logs.",
        )

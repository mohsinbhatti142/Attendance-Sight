"""Employee management API routes."""
import os
import cv2
import numpy as np
from typing import Optional
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_db
from src.db.models import Employee, FaceEncoding, Department
from src.api.schemas.employee import (
    EmployeeCreate, EmployeeUpdate, EmployeeResponse, EmployeeListResponse
)
from src.services.face_detection import face_detector
from src.services.face_matching import face_matcher
from src.utils.image_utils import save_face_image
from src.utils.logger import logger
from src.core.config import get_settings
from src.api.deps import require_admin, require_ai_ready

settings = get_settings()
router = APIRouter(prefix="/employees", tags=["Employees"], dependencies=[Depends(require_admin)])


def _employee_photo_url(employee: Employee) -> Optional[str]:
    if not employee.profile_image_url:
        return None
    normalized = employee.profile_image_url.replace("\\", "/")
    filename = os.path.basename(normalized)
    return f"/api/v1/biometric-images/{employee.id}/{filename}" if filename else None


@router.get("/departments/list")
async def list_departments(db: AsyncSession = Depends(get_db)):
    """List all company departments."""
    stmt = select(Department).order_by(Department.name)
    result = await db.execute(stmt)
    departments = result.scalars().all()
    return [{"id": d.id, "name": d.name, "code": d.code} for d in departments]


@router.get("/", response_model=EmployeeListResponse)
async def list_employees(
    skip: int = 0,
    limit: int = Query(50, ge=1, le=200),
    is_active: Optional[bool] = None,
    department_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all employees with optional filters."""
    stmt = select(Employee)
    if is_active is not None:
        stmt = stmt.where(Employee.is_active == is_active)
    if department_id:
        stmt = stmt.where(Employee.department_id == department_id)
    
    stmt = stmt.offset(skip).limit(limit).order_by(Employee.full_name)
    result = await db.execute(stmt)
    employees = result.scalars().all()
    
    count_stmt = select(Employee)
    if is_active is not None:
        count_stmt = count_stmt.where(Employee.is_active == is_active)
    count_result = await db.execute(count_stmt)
    total = len(count_result.scalars().all())
    
    items = []
    for employee in employees:
        item = EmployeeResponse.model_validate(employee)
        item.profile_image_url = _employee_photo_url(employee)
        items.append(item)
    return EmployeeListResponse(
        employees=items,
        total=total,
    )


@router.post("/", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
async def create_employee(
    employee: EmployeeCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new employee."""
    existing = await db.execute(
        select(Employee).where(Employee.employee_code == employee.employee_code)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Employee with code '{employee.employee_code}' already exists"
        )
    
    db_employee = Employee(**employee.model_dump())
    db.add(db_employee)
    await db.flush()
    await db.refresh(db_employee)
    
    logger.info(f"Employee created: {db_employee.employee_code} - {db_employee.full_name}")
    return EmployeeResponse.model_validate(db_employee)


@router.get("/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get employee by ID."""
    result = await db.execute(select(Employee).where(Employee.id == employee_id))
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    response = EmployeeResponse.model_validate(employee)
    response.profile_image_url = _employee_photo_url(employee)
    return response


@router.put("/{employee_id}", response_model=EmployeeResponse)
async def update_employee(
    employee_id: int,
    update: EmployeeUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update employee details."""
    result = await db.execute(select(Employee).where(Employee.id == employee_id))
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    update_data = update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(employee, key, value)
    
    await db.flush()
    await db.refresh(employee)

    # Sync streamer in-memory cache
    try:
        from src.services.streamer import streamer
        streamer.employee_name_cache[employee.id] = employee.full_name
        streamer.employee_code_cache[employee.id] = employee.employee_code
    except Exception:
        pass

    return EmployeeResponse.model_validate(employee)


@router.post("/{employee_id}/enroll-face", dependencies=[Depends(require_ai_ready)])
async def enroll_face(
    employee_id: int,
    file: UploadFile = File(..., description="Face image (JPEG/PNG)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Enroll an employee's face for recognition.
    """
    if not face_detector.is_loaded:
        raise HTTPException(status_code=503, detail="Face recognition model is not available")
    result = await db.execute(select(Employee).where(Employee.id == employee_id))
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    contents = await file.read(10 * 1024 * 1024 + 1)
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image exceeds the 10 MB limit")
    nparr = np.frombuffer(contents, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if image is None:
        raise HTTPException(status_code=400, detail="Invalid image file")
    if image.shape[0] * image.shape[1] > 25_000_000:
        raise HTTPException(status_code=413, detail="Image dimensions exceed the 25 megapixel limit")
    
    faces = face_detector.detect_and_embed(image)
    
    if not faces:
        raise HTTPException(
            status_code=400,
            detail="No face detected in the image. Please upload a clear face photo."
        )
    
    best_face = faces[0]
    
    if best_face.embedding is None:
        raise HTTPException(
            status_code=400,
            detail="Could not generate face embedding. Please try a clearer image."
        )
    
    image_path = save_face_image(image, employee_id, settings.face_images_dir)
    embedding_bytes = best_face.embedding.astype(np.float32).tobytes()
    
    face_encoding = FaceEncoding(
        employee_id=employee_id,
        embedding=embedding_bytes,
        image_path=image_path,
        quality_score=best_face.quality_score,
        is_primary=True,
    )
    db.add(face_encoding)
    await db.flush()
    
    face_matcher.add_embedding(employee_id, best_face.embedding)
    face_matcher.save_index()
    
    logger.info(
        f"Face enrolled for employee {employee_id} ({employee.full_name}) | "
        f"Quality: {best_face.quality_score:.2f} | Confidence: {best_face.confidence:.4f}"
    )
    
    return {
        "message": f"Face enrolled successfully for {employee.full_name}",
        "employee_id": employee_id,
        "quality_score": best_face.quality_score,
        "detection_confidence": best_face.confidence,
        "total_encodings": len(employee.face_encodings) + 1 if employee.face_encodings else 1,
    }


@router.delete("/{employee_id}", dependencies=[Depends(require_ai_ready)])
async def delete_employee(
    employee_id: int,
    permanent: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete an employee or soft-deactivate."""
    result = await db.execute(select(Employee).where(Employee.id == employee_id))
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    emp_name = employee.full_name

    # Remove embeddings from FAISS
    face_matcher.remove_employee(employee_id)
    face_matcher.save_index()

    # Purge streamer live sessions and events
    from src.services.streamer import streamer
    streamer.remove_employee(employee_id)

    if permanent:
        from sqlalchemy import delete
        from src.db.models import FaceEncoding, AttendanceLog
        # Cascade delete face encodings and attendance logs
        await db.execute(delete(FaceEncoding).where(FaceEncoding.employee_id == employee_id))
        await db.execute(delete(AttendanceLog).where(AttendanceLog.employee_id == employee_id))
        await db.delete(employee)
        await db.commit()
        logger.info(f"🗑️ Permanently deleted employee {emp_name} (ID: {employee_id})")
        return {"message": f"Employee {emp_name} permanently deleted"}
    else:
        employee.is_active = False
        await db.commit()
        return {"message": f"Employee {emp_name} deactivated"}

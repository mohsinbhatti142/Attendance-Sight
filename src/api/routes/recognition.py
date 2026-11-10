"""Face recognition API routes — identify or verify faces."""
import numpy as np
import cv2
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi import status
from src.services.face_detection import face_detector
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_db
from src.db.models import Employee
from src.services.face_detection import face_detector
from src.services.face_matching import face_matcher
from src.utils.logger import logger
from src.api.deps import require_admin, require_ai_ready

router = APIRouter(
    prefix="/recognition",
    tags=["Recognition"],
    dependencies=[Depends(require_admin), Depends(require_ai_ready)],
)


@router.post("/identify")
async def identify_face(
    file: UploadFile = File(..., description="Image containing a face to identify"),
    db: AsyncSession = Depends(get_db),
):
    """
    Identify a person from a face image.
    1. Detects face(s) in the uploaded image
    2. Generates embedding(s)
    3. Searches FAISS index for matches
    4. Returns identified employee(s) with confidence scores
    """
    if not face_detector.is_loaded:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Face recognition model is not available")
    contents = await file.read(10 * 1024 * 1024 + 1)
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image exceeds the 10 MB limit")
    nparr = np.frombuffer(contents, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if image is None:
        raise HTTPException(status_code=400, detail="Invalid image file")
    
    faces = face_detector.detect_and_embed(image)
    
    if not faces:
        return {"identified": False, "message": "No face detected in image", "results": []}
    
    results = []
    for face in faces:
        if face.embedding is None:
            continue
        
        match = face_matcher.identify(face.embedding)
        
        if match and match.is_match:
            emp_result = await db.execute(
                select(Employee).where(Employee.id == match.employee_id)
            )
            employee = emp_result.scalar_one_or_none()
            
            results.append({
                "identified": True,
                "employee_id": match.employee_id,
                "employee_name": employee.full_name if employee else "Unknown",
                "employee_code": employee.employee_code if employee else "N/A",
                "confidence": round(match.confidence, 4),
                "bbox": face.bbox.tolist(),
            })
        else:
            results.append({
                "identified": False,
                "confidence": round(match.confidence, 4) if match else 0.0,
                "bbox": face.bbox.tolist(),
                "message": "Face not recognized",
            })
    
    return {
        "total_faces": len(faces),
        "identified_count": sum(1 for r in results if r.get("identified")),
        "results": results,
    }

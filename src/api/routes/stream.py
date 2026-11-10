"""
Streaming & Web Kiosk API Routes.

Connects the async video streamer and GPU engine to the web dashboard.
Provides real-time MJPEG video, biometric enrollment, and event polling.
"""
import os
import time
import asyncio
import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.streamer import streamer
from src.services.face_detection import face_detector
from src.services.face_matching import face_matcher
from src.services.attendance import attendance_service
from src.db.database import get_db
from src.db.models import Camera, CameraType, Employee, FaceEncoding, EventType, AttendanceLog
from src.utils.image_utils import save_face_image
from src.core.config import get_settings
from src.utils.logger import logger
from src.api.deps import require_admin, require_ai_ready
from src.db.models import AdminUser

settings = get_settings()
router = APIRouter(prefix="/stream", tags=["Streaming & Kiosk"], dependencies=[Depends(require_admin)])
# WebSockets are authenticated inside their handler. Keep this router separate
# so the HTTP-only require_admin(Request, ...) dependency is not applied to it.
websocket_router = APIRouter(prefix="/stream", tags=["Streaming & Kiosk"])


class QuickEnrollRequest(BaseModel):
    full_name: str
    employee_code: str
    department: Optional[str] = None
    designation: Optional[str] = None


def generate_frames():
    """Generator for smooth MJPEG streaming to browser."""
    while True:
        frame_bytes = streamer.get_latest_jpeg()
        if frame_bytes is None:
            time.sleep(0.03)
            continue

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.02)  # ~45-50 FPS stream


@router.get("/video_feed", dependencies=[Depends(require_ai_ready)])
async def video_feed(request: Request):
    """Live video feed endpoint with GPU detection overlay."""
    if not streamer.is_running:
        source = request.app.state.camera_source
        if source is None:
            raise HTTPException(
                status_code=409,
                detail="Select a camera in Camera & shift setup before opening the live feed.",
            )
        streamer.start(source=source)
    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@websocket_router.websocket("/ws")
async def websocket_telemetry(websocket: WebSocket):
    """
    Real-time bidirectional WebSocket stream for Kiosk Telemetry.
    Streams current FPS, detected faces (bboxes, names, liveness), and live punch cards.
    """
    from src.core.security import verify_token
    from jose import JWTError
    token = websocket.cookies.get("attendsight_session")
    try:
        payload = verify_token(token) if token else {}
        admin_id = int(payload.get("sub", 0))
        from src.db.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            admin = await db.get(AdminUser, admin_id)
            if not admin or not admin.is_active:
                raise ValueError("Inactive session")
    except (JWTError, TypeError, ValueError):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        while True:
            telemetry = streamer.get_telemetry()
            telemetry["model_ready"] = websocket.app.state.ai_status == "ready"
            telemetry["ai_status"] = websocket.app.state.ai_status
            telemetry["model_provider"] = face_detector.provider_name
            await websocket.send_json(telemetry)
            await asyncio.sleep(0.1)  # 10 Hz refresh
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"WebSocket client disconnected: {e}")


@router.get("/live_status")
async def live_status(request: Request, db: AsyncSession = Depends(get_db)):
    """Poll live kiosk attendance events, enrolled count, and today's summary."""
    from datetime import date, datetime, time
    from sqlalchemy import and_

    # Get active employees from database
    emp_res = await db.execute(select(Employee).where(Employee.is_active == True))
    active_employees = emp_res.scalars().all()
    active_emp_ids = set(e.id for e in active_employees)
    total_enrolled = len(active_employees)

    with streamer.lock:
        recognized_name = streamer.latest_recognized_name
        streamer.latest_recognized_name = None  # Reset after reading
        greeting_event = streamer.latest_greeting_event
        if greeting_event and datetime.now().timestamp() - greeting_event["created_at"] > 30:
            greeting_event = None

    # The database is authoritative so the feed works across restarts and local demo mode.
    recent_rows = await db.execute(
        select(AttendanceLog, Employee)
        .join(Employee, AttendanceLog.employee_id == Employee.id)
        .where(Employee.is_active.is_(True))
        .order_by(AttendanceLog.timestamp.desc())
        .limit(15)
    )
    recent_events = []
    for record, employee in recent_rows.all():
        timestamp = record.timestamp
        recent_events.append({
            "event_id": record.id,
            "employee_id": employee.id,
            "name": employee.full_name,
            "code": employee.employee_code,
            "type": record.event_type.value,
            "time": timestamp.strftime("%I:%M:%S %p"),
            "date": timestamp.strftime("%d %b %Y"),
            "confidence": round(record.confidence * 100, 1),
            "liveness_score": round((record.liveness_score or 0) * 100, 1),
            "snapshot": f"/api/v1/audit-images/{record.id}" if record.face_image_path else None,
        })

    today_start = datetime.combine(date.today(), time.min)
    log_stmt = select(AttendanceLog.employee_id).where(
        and_(
            AttendanceLog.timestamp >= today_start,
            AttendanceLog.event_type == EventType.CHECK_IN,
            AttendanceLog.employee_id.in_(active_emp_ids) if active_emp_ids else False
        )
    ).distinct()
    today_present_list = (await db.execute(log_stmt)).scalars().all() if active_emp_ids else []
    today_present = len(today_present_list)

    return {
        "status": request.app.state.ai_status,
        "ai_status": request.app.state.ai_status,
        "model_status": request.app.state.model_status,
        "model_provider": face_detector.provider_name,
        "matcher_status": request.app.state.matcher_status,
        "model_ready": request.app.state.ai_status == "ready",
        "camera_active": streamer.is_running and streamer.latest_jpeg_bytes is not None,
        "fps": round(streamer.fps, 1) if streamer.latest_jpeg_bytes is not None else 0.0,
        "total_enrolled": total_enrolled,
        "today_present": today_present,
        "latest_recognized": recognized_name,
        "greeting_event": greeting_event,
        "events": recent_events,
    }


@router.post("/enroll_current_frame", dependencies=[Depends(require_ai_ready)])
async def enroll_current_frame(
    request: QuickEnrollRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Biometric Enrollment from Live Camera Frame.
    1. Captures live frame from streamer
    2. Runs RetinaFace on GPU
    3. Extracts 512-d ArcFace embedding
    4. Saves into PostgreSQL DB & FAISS index
    """
    if not face_detector.is_loaded:
        raise HTTPException(status_code=503, detail="Face recognition model is not available")
    raw_frame = streamer.capture_high_res_face()
    if raw_frame is None:
        raise HTTPException(status_code=400, detail="Camera feed not available. Please wait a moment.")

    # Detect faces
    faces = face_detector.detect_and_embed(raw_frame)
    if not faces:
        raise HTTPException(status_code=400, detail="No face detected. Please face the camera clearly.")

    best_face = faces[0]
    if best_face.embedding is None:
        raise HTTPException(status_code=400, detail="Could not compute face vector. Please improve lighting.")

    # Check for duplicate employee code
    stmt = select(Employee).where(Employee.employee_code == request.employee_code)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    
    if existing:
        db_emp = existing
    else:
        db_emp = Employee(
            employee_code=request.employee_code,
            full_name=request.full_name,
            designation=request.designation,
        )
        db.add(db_emp)
        await db.flush()
        await db.refresh(db_emp)

    emp_id = db_emp.id

    # Save face image
    img_path = save_face_image(raw_frame, emp_id, settings.face_images_dir)

    # Save Face Encoding to Database
    encoding_bytes = best_face.embedding.astype(np.float32).tobytes()
    face_encoding = FaceEncoding(
        employee_id=emp_id,
        embedding=encoding_bytes,
        image_path=img_path,
        quality_score=best_face.quality_score,
        is_primary=True,
    )
    db.add(face_encoding)
    await db.flush()

    # Add to FAISS Vector Index
    face_matcher.add_embedding(emp_id, best_face.embedding)
    face_matcher.save_index()

    logger.info(f"✅ Enrolled {request.full_name} (EMP #{emp_id}) into Database & FAISS!")

    return {
        "success": True,
        "message": f"Employee {request.full_name} enrolled successfully!",
        "employee_id": emp_id,
        "quality_score": round(best_face.quality_score, 1),
    }


@router.get("/camera_source")
async def get_camera_source(db: AsyncSession = Depends(get_db)):
    camera = await db.scalar(
        select(Camera)
        .where(Camera.is_active.is_(True))
        .order_by(Camera.id)
        .limit(1)
    )
    return {"source": camera.source if camera else None, "configured": camera is not None}


@router.delete("/camera_source")
async def clear_camera_source(request: Request, db: AsyncSession = Depends(get_db)):
    active_cameras = (
        await db.scalars(select(Camera).where(Camera.is_active.is_(True)))
    ).all()
    for camera in active_cameras:
        camera.is_active = False
    await db.commit()
    request.app.state.camera_source = None
    await asyncio.to_thread(streamer.stop)
    return {"configured": False, "message": "Camera selection cleared."}


@router.post("/set_camera_source")
async def set_camera_source(source: str, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Save the selected webcam or RTSP source and start it when AI is ready.
    """
    source = source.strip()
    if not source or len(source) > 500:
        raise HTTPException(status_code=422, detail="Choose a valid camera source.")
    if source.isdigit():
        parsed_source: int | str = int(source)
        if parsed_source > 15:
            raise HTTPException(status_code=422, detail="Webcam index must be between 0 and 15.")
        camera_name = f"Webcam {parsed_source}"
    elif source.lower().startswith("rtsp://"):
        parsed_source = source
        camera_name = "Network camera"
    else:
        raise HTTPException(
            status_code=422,
            detail="Use a webcam index or an RTSP camera address.",
        )

    active_cameras = (
        await db.scalars(select(Camera).where(Camera.is_active.is_(True)))
    ).all()
    selected_camera = next((camera for camera in active_cameras if camera.source == source), None)
    for camera in active_cameras:
        camera.is_active = camera is selected_camera
    if selected_camera is None:
        selected_camera = Camera(
            name=camera_name,
            source=source,
            camera_type=CameraType.BOTH,
            is_active=True,
        )
        db.add(selected_camera)
    await db.commit()

    request.app.state.camera_source = parsed_source
    if request.app.state.ai_status == "ready":
        await asyncio.to_thread(streamer.stop)
        await asyncio.to_thread(streamer.start, source=parsed_source)
        message = "Camera saved and started."
    else:
        message = "Camera saved. It will start when the AI services are ready."
    return {"message": message, "source": source, "configured": True}


# =====================================================================
# 3D KYC MULTI-ANGLE BIOMETRIC CALIBRATION ENGINE (FOR HIGH-ANGLE CCTV)
# =====================================================================
import uuid

kyc_sessions: dict[str, dict] = {}


class KycStartRequest(BaseModel):
    full_name: str
    employee_code: str
    department: Optional[str] = None
    designation: Optional[str] = None


class KycSampleRequest(BaseModel):
    session_id: str
    angle: str  # 'center', 'left', 'right', 'tilt'


class KycCommitRequest(BaseModel):
    session_id: str


KYC_SAMPLES_PER_ANGLE = 3


async def _find_duplicate_face(embedding: np.ndarray, db: AsyncSession):
    """Return an existing employee matching any previously saved face template."""
    matches = face_matcher.search(embedding, top_k=1)
    if not matches or not matches[0].is_match:
        return None
    employee = await db.get(Employee, matches[0].employee_id)
    if employee:
        return employee, matches[0].confidence
    return None


@router.post("/kyc/start", dependencies=[Depends(require_ai_ready)])
async def kyc_start(request: KycStartRequest, db: AsyncSession = Depends(get_db)):
    """Initialize a multi-angle KYC calibration session."""
    if not face_detector.is_loaded:
        raise HTTPException(status_code=503, detail="Face recognition model is not available")
    employee_code = request.employee_code.strip()
    existing = await db.execute(select(Employee).where(func.lower(Employee.employee_code) == employee_code.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Employee code '{employee_code}' is already registered. Open the existing employee profile instead.")
    session_id = str(uuid.uuid4())
    kyc_sessions[session_id] = {
        "full_name": request.full_name,
        "employee_code": employee_code,
        "department": request.department,
        "designation": request.designation,
        "angles": {"center": [], "left": [], "right": []},
        "created_at": time.time(),
    }
    return {"session_id": session_id, "status": "ready"}


@router.post("/kyc/sample", dependencies=[Depends(require_ai_ready)])
async def kyc_sample(request: KycSampleRequest, db: AsyncSession = Depends(get_db)):
    """
    Capture and validate a single facial pose during the KYC wizard.
    Extracts 512-d ArcFace vector and assesses pose quality.
    """
    if not face_detector.is_loaded:
        raise HTTPException(status_code=503, detail="Face recognition model is not available")
    session = kyc_sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="KYC session expired or invalid.")

    raw_frame = streamer.capture_high_res_face()
    if raw_frame is None:
        raise HTTPException(status_code=400, detail="Camera stream unavailable.")

    faces = face_detector.detect_and_embed(raw_frame)
    if not faces:
        return {
            "success": False,
            "angle": request.angle,
            "message": "No face detected. Please ensure good lighting and look toward camera.",
        }

    best_face = faces[0]
    if best_face.embedding is None:
        return {
            "success": False,
            "angle": request.angle,
            "message": "Face vector extraction failed. Hold still for a second.",
        }

    # STRICT 3D AI HEAD POSE VERIFICATION
    target_angle = request.angle.lower()
    pose_valid = False
    fail_guidance = ""

    # DetectedFace exposes pose angles in degrees. The previous ratio
    # attributes never existed, causing every enrollment capture to raise
    # AttributeError and appear as a generic camera capture failure.
    yaw = best_face.yaw
    pitch = best_face.pitch

    if target_angle == "center":
        if abs(yaw) > 16.0:
            fail_guidance = f"Head turned ({'Left' if yaw < 0 else 'Right'}). Please look directly forward into camera."
        elif abs(pitch) > 18.0:
            fail_guidance = "Head tilted. Please look straight level into the lens."
        else:
            pose_valid = True

    elif target_angle == "left":
        # Turning head to left: yaw must be noticeably shifted
        if yaw > -12.0:
            fail_guidance = "Head not turned! Please turn your head to the LEFT side."
        else:
            pose_valid = True

    elif target_angle == "right":
        # Turning head to right: yaw must be noticeably shifted
        if yaw < 12.0:
            fail_guidance = "Head not turned! Please turn your head to the RIGHT side."
        else:
            pose_valid = True

    elif target_angle == "tilt":
        # Tilting head UP for CCTV ceiling view: pitch ratio drops as chin elevates
        if pitch > -12.0:
            fail_guidance = "Head not tilted! Please tilt your chin UP toward the ceiling."
        else:
            pose_valid = True

    if not pose_valid:
        return {
            "success": False,
            "angle": request.angle,
            "message": fail_guidance,
            "yaw": round(yaw, 2),
            "pitch": round(pitch, 2),
            "detected_pose": best_face.pose_label,
        }

    if best_face.quality_score < 40.0:
        return {"success": False, "angle": request.angle, "message": "Image quality is low. Face the camera in brighter, even lighting."}

    duplicate = await _find_duplicate_face(best_face.embedding, db)
    if duplicate:
        employee, similarity = duplicate
        raise HTTPException(
            status_code=409,
            detail=f"This face already matches {employee.full_name} ({employee.employee_code}) at {similarity:.0%}. Use the existing employee profile instead of creating a duplicate."
        )

    angle_samples = session["angles"].setdefault(request.angle, [])
    if any(float(np.dot(sample["embedding"], best_face.embedding)) > 0.995 for sample in angle_samples):
        return {"success": False, "angle": request.angle, "sample_count": len(angle_samples), "message": "This frame is almost identical to the last one. Slightly change your expression or head position and capture again."}

    sample_number = len(angle_samples) + 1

    # Crop thumbnail preview
    bbox = best_face.bbox.astype(int)
    h, w = raw_frame.shape[:2]
    x1, y1 = max(0, bbox[0] - 20), max(0, bbox[1] - 20)
    x2, y2 = min(w, bbox[2] + 20), min(h, bbox[3] + 20)
    crop = raw_frame[y1:y2, x1:x2]
    
    # Save preview image
    preview_dir = os.path.join("data", "snapshots")
    os.makedirs(preview_dir, exist_ok=True)
    preview_filename = f"kyc_{request.session_id[:8]}_{request.angle}_{sample_number}.jpg"
    preview_path = os.path.join(preview_dir, preview_filename)
    cv2.imwrite(preview_path, crop)

    angle_samples.append({
        "embedding": best_face.embedding,
        "quality": float(best_face.quality_score),
        "frame": raw_frame,
        "preview_url": f"/api/v1/enrollment-previews/{preview_filename}",
    })
    sample_count = len(angle_samples)

    return {
        "success": True,
        "angle": request.angle,
        "quality": round(best_face.quality_score, 1),
        "preview_url": f"/api/v1/enrollment-previews/{preview_filename}",
        "sample_count": sample_count,
        "required_samples": KYC_SAMPLES_PER_ANGLE,
        "message": f"Recorded {request.angle.upper()} sample {sample_count} of {KYC_SAMPLES_PER_ANGLE}.",
    }


@router.post("/kyc/commit", dependencies=[Depends(require_ai_ready)])
async def kyc_commit(request: KycCommitRequest, db: AsyncSession = Depends(get_db)):
    """
    Persist all captured multi-angle vectors into Database and FAISS.
    Ensures employee can be recognized by ceiling CCTV cameras at any angle.
    """
    session = kyc_sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="KYC session expired or invalid.")

    angles = session.get("angles", {})
    missing_angles = [angle.upper() for angle in ("center", "left", "right") if len(angles.get(angle, [])) < KYC_SAMPLES_PER_ANGLE]
    if missing_angles:
        raise HTTPException(status_code=400, detail=f"Capture {KYC_SAMPLES_PER_ANGLE} clear samples for each angle first. Still needed: {', '.join(missing_angles)}.")

    emp_code = session["employee_code"]
    full_name = session["full_name"]
    designation = session.get("designation")

    # Check for existing employee
    stmt = select(Employee).where(func.lower(Employee.employee_code) == emp_code.lower())
    db_emp = (await db.execute(stmt)).scalar_one_or_none()
    if db_emp:
        raise HTTPException(status_code=409, detail=f"Employee code '{emp_code}' is already registered. Open the existing employee profile instead.")

    all_samples = [sample for angle_samples in angles.values() for sample in angle_samples]
    for sample in all_samples:
        duplicate = await _find_duplicate_face(sample["embedding"], db)
        if duplicate:
            employee, similarity = duplicate
            raise HTTPException(
                status_code=409,
                detail=f"This face already matches {employee.full_name} ({employee.employee_code}) at {similarity:.0%}. No employee was saved. Open the existing profile instead."
            )

    best_sample = max(all_samples, key=lambda item: item["quality"])
    db_emp = Employee(employee_code=emp_code, full_name=full_name, designation=designation)
    db.add(db_emp)
    await db.flush()
    await db.refresh(db_emp)
    emp_id = db_emp.id
    # Persist each recorded angle
    recorded_count = 0
    index_updates = []
    for angle_name, angle_samples in angles.items():
        for angle_data in angle_samples:
            embedding = angle_data["embedding"]
            frame = angle_data["frame"]
            quality = angle_data["quality"]

            img_path = save_face_image(frame, emp_id, settings.face_images_dir)
            if frame is best_sample["frame"]:
                db_emp.profile_image_url = _to_web_path(img_path)
            encoding_bytes = embedding.astype(np.float32).tobytes()

            face_encoding = FaceEncoding(
                employee_id=emp_id,
                embedding=encoding_bytes,
                image_path=img_path,
                quality_score=quality,
                pose_type=angle_name.upper(),
                liveness_score=1.0,
                is_primary=(frame is best_sample["frame"]),
            )
            db.add(face_encoding)
            index_updates.append(embedding)
            recorded_count += 1

    await db.commit()
    streamer.employee_name_cache[emp_id] = full_name
    streamer.employee_code_cache[emp_id] = emp_code
    for embedding in index_updates:
        face_matcher.add_embedding(emp_id, embedding)
    face_matcher.save_index()
    kyc_sessions.pop(request.session_id, None)

    logger.info(f"🏆 KYC COMPLETE: Enrolled {full_name} (EMP #{emp_id}) with {recorded_count} face samples across 3 angles!")

    return {
        "success": True,
        "message": f"Successfully enrolled {full_name} with {recorded_count} face samples across 3 angles!",
        "employee_id": emp_id,
        "angles_count": recorded_count,
    }


# =====================================================================
# SMART VIDEO BURST MULTI-FRAME ENROLLMENT (5-SECOND ACTIVE SCAN)
# =====================================================================
def _to_web_path(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    norm = path.replace("\\", "/")
    return norm if norm.startswith("/") else f"/{norm}"


burst_sessions: dict[str, dict] = {}


class BurstStartRequest(BaseModel):
    full_name: str
    employee_code: str
    department: Optional[str] = "General"
    designation: Optional[str] = "Staff"
    phone: Optional[str] = None
    email: Optional[str] = None


class BurstSampleRequest(BaseModel):
    session_id: str


class BurstCommitRequest(BaseModel):
    session_id: str


@router.post("/burst/start", dependencies=[Depends(require_ai_ready)])
async def burst_start(request: BurstStartRequest):
    """Start a smart multi-frame video burst enrollment session."""
    if not face_detector.is_loaded:
        raise HTTPException(status_code=503, detail="Face recognition model is not available")
    session_id = str(uuid.uuid4())
    burst_sessions[session_id] = {
        "full_name": request.full_name,
        "employee_code": request.employee_code,
        "department": request.department,
        "designation": request.designation,
        "phone": request.phone,
        "email": request.email,
        "samples": [],
        "created_at": time.time(),
    }
    return {"session_id": session_id, "status": "ready"}


@router.post("/burst/sample", dependencies=[Depends(require_ai_ready)])
async def burst_sample(request: BurstSampleRequest):
    """Capture a single burst frame, extract face vector, and store thumbnail preview."""
    if not face_detector.is_loaded:
        raise HTTPException(status_code=503, detail="Face recognition model is not available")
    session = burst_sessions.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Burst session expired or invalid.")

    raw_frame = streamer.capture_high_res_face()
    if raw_frame is None:
        raise HTTPException(status_code=400, detail="Camera stream unavailable.")

    faces = face_detector.detect_and_embed(raw_frame)
    if not faces:
        return {"success": False, "message": "No face detected. Keep face inside frame."}

    best_face = faces[0]
    if best_face.embedding is None:
        return {"success": False, "message": "Sampling face vectors..."}

    if best_face.quality_score < 40.0:
        return {"success": False, "message": "Face clarity low. Adjust lighting or face camera."}

    # Crop thumbnail
    bbox = best_face.bbox.astype(int)
    h, w = raw_frame.shape[:2]
    x1, y1 = max(0, bbox[0] - 15), max(0, bbox[1] - 15)
    x2, y2 = min(w, bbox[2] + 15), min(h, bbox[3] + 15)
    crop = raw_frame[y1:y2, x1:x2]

    idx = len(session["samples"]) + 1
    preview_dir = os.path.join("data", "snapshots")
    os.makedirs(preview_dir, exist_ok=True)
    filename = f"burst_{request.session_id[:8]}_{idx}.jpg"
    filepath = os.path.join(preview_dir, filename)
    cv2.imwrite(filepath, crop)

    sample_entry = {
        "embedding": best_face.embedding,
        "quality": float(best_face.quality_score),
        "pose": best_face.pose_label,
        "frame": raw_frame,
        "thumb_url": f"/api/v1/enrollment-previews/{filename}"
    }
    session["samples"].append(sample_entry)

    return {
        "success": True,
        "count": len(session["samples"]),
        "thumb_url": f"/api/v1/enrollment-previews/{filename}",
        "quality": round(best_face.quality_score, 1),
        "pose": best_face.pose_label,
        "message": f"Frame {idx} captured ({best_face.pose_label})"
    }


@router.post("/burst/commit", dependencies=[Depends(require_ai_ready)])
async def burst_commit(request: BurstCommitRequest, db: AsyncSession = Depends(get_db)):
    """Save the burst-scanned employee profile and all sampled face vectors into DB & FAISS."""
    session = burst_sessions.pop(request.session_id, None)
    if not session:
        raise HTTPException(status_code=404, detail="Burst session expired or invalid.")

    samples = session.get("samples", [])
    if not samples:
        raise HTTPException(status_code=400, detail="No face frames were captured. Please run scan first.")

    emp_code = session["employee_code"]
    full_name = session["full_name"]
    designation = session.get("designation")
    phone = session.get("phone")
    email = session.get("email")

    stmt = select(Employee).where(Employee.employee_code == emp_code)
    db_emp = (await db.execute(stmt)).scalar_one_or_none()

    if not db_emp:
        db_emp = Employee(
            employee_code=emp_code,
            full_name=full_name,
            designation=designation,
            phone=phone,
            email=email,
            is_active=True,
        )
        db.add(db_emp)
        await db.flush()
        await db.refresh(db_emp)
    else:
        db_emp.full_name = full_name
        db_emp.designation = designation
        db_emp.phone = phone
        db_emp.email = email
        db_emp.is_active = True

    emp_id = db_emp.id

    # Select best quality frame as primary profile picture
    best_idx = max(range(len(samples)), key=lambda idx: samples[idx]["quality"])
    best_sample = samples[best_idx]
    primary_img_path = save_face_image(best_sample["frame"], emp_id, settings.face_images_dir)
    db_emp.profile_image_url = _to_web_path(primary_img_path)

    # Persist sample embeddings into DB & FAISS (up to 40 diverse vectors)
    added_vectors = 0
    for i, s in enumerate(samples[:40]):
        embedding = s["embedding"]
        frame = s["frame"]
        quality = s["quality"]

        img_path = save_face_image(frame, emp_id, settings.face_images_dir)
        encoding_bytes = embedding.astype(np.float32).tobytes()

        face_encoding = FaceEncoding(
            employee_id=emp_id,
            embedding=encoding_bytes,
            image_path=img_path,
            quality_score=quality,
            pose_type="MULTI_BURST",
            liveness_score=1.0,
            is_primary=(i == best_idx),
        )
        db.add(face_encoding)
        face_matcher.add_embedding(emp_id, embedding)
        added_vectors += 1

    await db.commit()
    face_matcher.save_index()

    # Update streamer cache
    streamer.employee_name_cache[emp_id] = f"{full_name} ({emp_code})"

    logger.info(f"🏆 BURST ENROLLMENT COMPLETE: Registered {full_name} with {added_vectors} vectors!")

    return {
        "success": True,
        "message": f"Successfully enrolled {full_name} with {added_vectors} biometric vectors!",
        "employee_id": emp_id,
        "vectors_count": added_vectors,
        "profile_url": _to_web_path(primary_img_path),
    }

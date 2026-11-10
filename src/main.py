"""Attendance-Sight private local attendance and face-recognition service."""
import os
import sys
import asyncio
import numpy as np
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from fastapi import Depends, HTTPException

from src.core.config import get_settings
from src.utils.logger import logger, setup_logger
from src.db.database import init_db, AsyncSessionLocal, engine, get_db
from src.db.models import AdminUser, Camera, FaceEncoding, AttendanceLog, Employee
from src.api.deps import require_admin
from src.api.routes import auth
from sqlalchemy import select
from src.services.face_detection import face_detector
from src.services.face_matching import face_matcher
from src.services.streamer import streamer

# Import routers
from src.api.routes import employees, attendance, cameras, recognition, stream

settings = get_settings()
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
STATIC_DIR = RESOURCE_DIR / "static"


async def initialize_ai(app: FastAPI) -> None:
    """Load recognition models, rebuild the face index, then start the camera."""
    try:
        logger.info("🧠 Loading face detection & recognition models...")
        await asyncio.to_thread(face_detector.load_model)
        app.state.model_status = "ready"
        logger.info("✅ Face detection model loaded")
    except Exception:
        app.state.model_status = "unavailable"
        logger.exception("Face detector loading error")

    try:
        logger.info("🔍 Initializing FAISS face matching index...")
        await asyncio.to_thread(face_matcher.initialize)
        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    select(FaceEncoding.employee_id, FaceEncoding.embedding)
                )
            ).all()
        saved_embeddings = {}
        for employee_id, embedding_bytes in rows:
            embedding = np.frombuffer(embedding_bytes, dtype=np.float32)
            if embedding.size == 512:
                saved_embeddings.setdefault(employee_id, []).append(embedding.copy())
        await asyncio.to_thread(face_matcher.rebuild_index, saved_embeddings)
        await asyncio.to_thread(face_matcher.save_index)
        app.state.matcher_status = "ready"
        logger.info(
            f"✅ FAISS ready ({face_matcher.total_embeddings} embeddings, "
            f"{face_matcher.total_employees} employees)"
        )
    except Exception:
        app.state.matcher_status = "unavailable"
        logger.exception("FAISS initialization error")

    if (
        app.state.model_status == "ready"
        and app.state.matcher_status == "ready"
        and app.state.camera_source is not None
    ):
        try:
            logger.info("🎥 Starting camera and face recognition services...")
            await asyncio.to_thread(streamer.start, source=app.state.camera_source)
            logger.info("✅ Camera streamer active (zero-lag async pipeline)")
        except Exception:
            logger.exception("Camera streamer failed to start")
    elif app.state.camera_source is None:
        logger.info("Camera startup skipped until an administrator selects a source.")

    app.state.ai_status = (
        "ready"
        if app.state.model_status == "ready" and app.state.matcher_status == "ready"
        else "unavailable"
    )
    if app.state.ai_status == "ready":
        logger.info("✅ AI services are READY")
    else:
        logger.error("AI services did not become ready; check the preceding startup errors.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    # === STARTUP ===
    setup_logger()
    logger.info("=" * 60)
    logger.info("🚀 Attendance-Sight is starting...")
    logger.info("=" * 60)
    
    # Create required directories
    for directory in [settings.face_images_dir, settings.model_weights_dir, settings.faiss_index_dir, "logs"]:
        os.makedirs(directory, exist_ok=True)
    
    # Initialize database
    try:
        logger.info("📦 Initializing database...")
        await init_db()
        async with AsyncSessionLocal() as session:
            saved_camera_source = await session.scalar(
                select(Camera.source)
                .where(Camera.is_active.is_(True))
                .order_by(Camera.id)
                .limit(1)
            )
            app.state.camera_source = (
                int(saved_camera_source)
                if saved_camera_source and saved_camera_source.isdigit()
                else saved_camera_source
            )
        logger.info("✅ Database ready")
    except Exception as e:
        logger.exception(f"Database startup failed: {e}")
        raise

    if settings.local_demo_mode:
        logger.warning("Local demo mode: camera/AI processing is intentionally disabled.")
        app.state.ai_status = "demo"
        app.state.model_status = "demo"
        app.state.matcher_status = "demo"
        try:
            yield
        finally:
            logger.info("Shutting down local demo session.")
            await engine.dispose()
        return

    app.state.ai_status = "loading"
    app.state.model_status = "loading"
    app.state.matcher_status = "loading"
    ai_task = asyncio.create_task(initialize_ai(app))
    app.state.ai_task = ai_task
    logger.info("=" * 60)
    logger.info("✅ Portal is ready; AI services are initializing in the background.")
    logger.info(f"🌐 Attendance-Sight: http://{settings.app_host}:{settings.app_port}")
    logger.info(f"📖 API Docs:   http://{settings.app_host}:{settings.app_port}/docs")
    logger.info("=" * 60)

    try:
        yield
    finally:
        logger.info("Shutting down...")
        await ai_task
        await asyncio.to_thread(streamer.stop)
        if app.state.matcher_status == "ready":
            try:
                await asyncio.to_thread(face_matcher.save_index)
                logger.info("FAISS index saved.")
            except Exception:
                logger.exception("Could not save FAISS index")
        await engine.dispose()
        logger.info("Goodbye!")


# Create FastAPI app
app = FastAPI(
    title="Attendance-Sight",
    description="Private local attendance and face-recognition application",
    version="1.3.4",
    lifespan=lifespan,
)
app.state.ai_status = "starting"
app.state.model_status = "starting"
app.state.matcher_status = "starting"
app.state.camera_source = None

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(employees.router, prefix="/api/v1")
app.include_router(attendance.router, prefix="/api/v1")
app.include_router(cameras.router, prefix="/api/v1")
app.include_router(recognition.router, prefix="/api/v1")
app.include_router(stream.router, prefix="/api/v1")
app.include_router(stream.websocket_router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")

# Only public UI assets are mounted. Biometric data is served through authorized handlers.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Return the Attendance-Sight icon at the conventional browser path."""
    return FileResponse(STATIC_DIR / "attendsight-icon.svg", media_type="image/svg+xml")


@app.get("/", tags=["Dashboard Portal"])
async def dashboard():
    """Attendance-Sight local attendance portal."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/v1/biometric-images/{employee_id}/{filename}", include_in_schema=False)
async def biometric_image(employee_id: int, filename: str, user: AdminUser = Depends(require_admin), db=Depends(get_db)):
    """Serve only an image tied to an enrolled encoding after admin authentication."""
    if filename != os.path.basename(filename) or not filename.lower().endswith(".jpg"):
        raise HTTPException(status_code=404, detail="Image not found")
    employee = await db.get(Employee, employee_id)
    candidates = (await db.scalars(select(FaceEncoding).where(FaceEncoding.employee_id == employee_id))).all()
    allowed_names = {os.path.basename(item.image_path.replace("\\", "/")) for item in candidates if item.image_path}
    if employee and employee.profile_image_url:
        allowed_names.add(os.path.basename(employee.profile_image_url.replace("\\", "/")))
    if filename not in allowed_names:
        raise HTTPException(status_code=404, detail="Image not found")
    path = os.path.abspath(os.path.join(settings.face_images_dir, str(employee_id), filename))
    root = os.path.abspath(settings.face_images_dir)
    if os.path.commonpath([path, root]) != root or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


@app.get("/api/v1/audit-images/{attendance_id}", include_in_schema=False)
async def audit_image(attendance_id: int, user: AdminUser = Depends(require_admin), db=Depends(get_db)):
    record = await db.get(AttendanceLog, attendance_id)
    if not record or not record.face_image_path:
        raise HTTPException(status_code=404, detail="Image not found")
    raw_path = record.face_image_path.replace("\\", os.sep).replace("/", os.sep)
    path = os.path.abspath(raw_path)
    root = os.path.abspath("data/snapshots")
    if os.path.commonpath([path, root]) != root or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


@app.get("/api/v1/enrollment-previews/{filename}", include_in_schema=False)
async def enrollment_preview(filename: str, user: AdminUser = Depends(require_admin)):
    if filename != os.path.basename(filename) or not filename.lower().endswith(".jpg"):
        raise HTTPException(status_code=404, detail="Image not found")
    path = os.path.abspath(os.path.join("data/snapshots", filename))
    root = os.path.abspath("data/snapshots")
    if os.path.commonpath([path, root]) != root or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


@app.middleware("http")
async def enforce_same_site_browser_requests(request, call_next):
    """Reject cross-site writes to cookie-authenticated APIs (CSRF defense)."""
    if request.method not in {"GET", "HEAD", "OPTIONS"} and request.url.path.startswith("/api/v1/"):
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            return Response(status_code=403, content="Cross-site request rejected")
    return await call_next(request)


@app.get("/health", tags=["Health"])
async def health_check():
    """Non-sensitive process liveness state."""
    return {
        "status": "degraded" if app.state.ai_status == "unavailable" else "healthy",
        "ai": app.state.ai_status,
        "model": app.state.model_status,
        "model_provider": face_detector.provider_name,
        "matcher": app.state.matcher_status,
        "camera": "running" if streamer.is_running else "stopped",
    }

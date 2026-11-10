"""
Camera Service - Manages video capture from multiple sources.

Supports:
1. Laptop webcam (index 0, 1, etc.)
2. USB cameras
3. IP cameras via RTSP (Hikvision, Dahua, CP Plus, etc.)
4. Video files (for testing)

Industry Standard: RTSP for IP cameras, DirectShow/V4L2 for local cameras.
"""
import os
import cv2
import time
import threading
import numpy as np
from typing import Optional, Callable
from dataclasses import dataclass
from enum import Enum

from src.core.config import get_settings
from src.utils.logger import logger

settings = get_settings()


class CameraSourceType(str, Enum):
    WEBCAM = "webcam"
    RTSP = "rtsp"
    VIDEO_FILE = "video_file"


@dataclass
class CameraInfo:
    """Camera connection information."""
    source: str             # Camera index ("0") or RTSP URL
    source_type: CameraSourceType
    name: str = "Camera"
    fps: float = 0.0
    width: int = 0
    height: int = 0
    is_connected: bool = False


class CameraStream:
    """
    Manages a single camera stream with thread-safe frame reading.
    
    Uses a separate thread to continuously read frames, so the main
    processing thread always gets the latest frame without blocking.
    """
    
    def __init__(self, source: str, name: str = "Camera"):
        self.name = name
        self._source = source
        self._source_type = self._detect_source_type(source)
        self._cap: Optional[cv2.VideoCapture] = None
        self._frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._frame_count = 0
        self._fps = 0.0
        self._last_fps_time = time.time()
    
    def _detect_source_type(self, source: str) -> CameraSourceType:
        """Detect camera source type from the source string."""
        if source.startswith("rtsp://") or source.startswith("rtsp:"):
            return CameraSourceType.RTSP
        elif source.endswith((".mp4", ".avi", ".mkv", ".mov")):
            return CameraSourceType.VIDEO_FILE
        else:
            return CameraSourceType.WEBCAM
    
    def connect(self) -> bool:
        """
        Connect to the camera source.
        
        Returns:
            True if connection successful
        """
        try:
            if self._source_type == CameraSourceType.WEBCAM:
                # Local camera (laptop webcam, USB camera)
                camera_idx = int(self._source)
                self._cap = cv2.VideoCapture(camera_idx, cv2.CAP_DSHOW)  # DirectShow for Windows
                self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, settings.camera_resolution_width)
                self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, settings.camera_resolution_height)
                self._cap.set(cv2.CAP_PROP_FPS, 30)
                
            elif self._source_type == CameraSourceType.RTSP:
                # IP Camera via RTSP
                # Use TCP transport for reliability (UDP can drop frames)
                os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
                self._cap = cv2.VideoCapture(self._source, cv2.CAP_FFMPEG)
                self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize latency
                
            elif self._source_type == CameraSourceType.VIDEO_FILE:
                self._cap = cv2.VideoCapture(self._source)
            
            if not self._cap.isOpened():
                logger.error(f"Failed to open camera: {self.name} ({self._source})")
                return False
            
            # Read test frame
            ret, frame = self._cap.read()
            if not ret:
                logger.error(f"Cannot read from camera: {self.name}")
                return False
            
            width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = self._cap.get(cv2.CAP_PROP_FPS)
            
            logger.info(
                f"Camera connected: {self.name} | "
                f"Source: {self._source_type.value} | "
                f"Resolution: {width}x{height} | "
                f"FPS: {fps}"
            )
            return True
            
        except Exception as e:
            logger.error(f"Camera connection error ({self.name}): {e}")
            return False
    
    def start(self):
        """Start the frame reading thread."""
        if self._cap is None or not self._cap.isOpened():
            if not self.connect():
                raise ConnectionError(f"Cannot connect to camera: {self.name}")
        
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        logger.info(f"Camera stream started: {self.name}")
    
    def _read_loop(self):
        """Continuous frame reading loop (runs in separate thread)."""
        while self._running:
            if self._cap is None or not self._cap.isOpened():
                logger.warning(f"Camera disconnected: {self.name}. Reconnecting...")
                time.sleep(2)
                self.connect()
                continue
            
            ret, frame = self._cap.read()
            if not ret:
                if self._source_type == CameraSourceType.VIDEO_FILE:
                    # Loop video files
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                else:
                    logger.warning(f"Frame read failed: {self.name}")
                    time.sleep(0.1)
                    continue
            
            with self._lock:
                self._frame = frame
                self._frame_count += 1
            
            # Calculate FPS
            now = time.time()
            elapsed = now - self._last_fps_time
            if elapsed >= 1.0:
                self._fps = self._frame_count / elapsed
                self._frame_count = 0
                self._last_fps_time = now
    
    def read(self) -> Optional[np.ndarray]:
        """
        Get the latest frame (thread-safe).
        
        Returns:
            Latest BGR frame or None if no frame available
        """
        with self._lock:
            return self._frame.copy() if self._frame is not None else None
    
    def stop(self):
        """Stop the camera stream."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        if self._cap:
            self._cap.release()
        logger.info(f"Camera stream stopped: {self.name}")
    
    def get_info(self) -> CameraInfo:
        """Get camera information."""
        return CameraInfo(
            source=self._source,
            source_type=self._source_type,
            name=self.name,
            fps=self._fps,
            width=int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)) if self._cap else 0,
            height=int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) if self._cap else 0,
            is_connected=self._cap is not None and self._cap.isOpened(),
        )
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    def __del__(self):
        self.stop()


class CameraManager:
    """
    Manages multiple camera streams.
    
    Usage:
        manager = CameraManager()
        manager.add_camera("0", "Laptop Webcam")  # Local camera
        manager.add_camera("rtsp://admin:pass@192.168.1.64:554/stream", "Entry Gate")  # IP camera
        manager.start_all()
        
        frame = manager.get_frame("Laptop Webcam")
    """
    
    def __init__(self):
        self._cameras: dict[str, CameraStream] = {}
    
    def add_camera(self, source: str, name: str) -> bool:
        """Add a camera source."""
        camera = CameraStream(source=source, name=name)
        if camera.connect():
            self._cameras[name] = camera
            logger.info(f"Camera added: {name}")
            return True
        return False
    
    def start_all(self):
        """Start all camera streams."""
        for name, camera in self._cameras.items():
            camera.start()
    
    def stop_all(self):
        """Stop all camera streams."""
        for name, camera in self._cameras.items():
            camera.stop()
    
    def get_frame(self, camera_name: str) -> Optional[np.ndarray]:
        """Get latest frame from a specific camera."""
        camera = self._cameras.get(camera_name)
        if camera:
            return camera.read()
        return None
    
    def get_all_frames(self) -> dict[str, Optional[np.ndarray]]:
        """Get latest frames from all cameras."""
        return {name: cam.read() for name, cam in self._cameras.items()}
    
    def list_cameras(self) -> list[CameraInfo]:
        """List all registered cameras with their status."""
        return [cam.get_info() for cam in self._cameras.values()]
    
    def remove_camera(self, name: str):
        """Remove and stop a camera."""
        if name in self._cameras:
            self._cameras[name].stop()
            del self._cameras[name]

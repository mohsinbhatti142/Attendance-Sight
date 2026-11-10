"""
Face Detection & Anti-Spoofing Liveness Pipeline using InsightFace ONNX Models:
- det_10g.onnx: RetinaFace face detection.
- w600k_r50.onnx: ArcFace 512-d feature embedding extraction.
- 1k3d68.onnx: 3D facial landmark alignment (68 3D points) & 3D head pose estimation.
- 2d106det.onnx: 2D dense landmark alignment (106 points).

Liveness Detection Architecture:
1. Passive Liveness (Eye Aspect Ratio - EAR): Continuous eye blink & micro-flutter detection.
2. Active Liveness (3D Landmark Analysis): 3D Head Pose (Yaw, Pitch, Roll) and Z-Depth variance (anti-photo/screen).
3. Confidence & Anti-Spoof thresholding.
"""
import os
import time
import cv2
import numpy as np
from typing import Optional, List, Tuple, Dict
from dataclasses import dataclass, field

from src.core.config import get_settings
from src.utils.logger import logger

settings = get_settings()


@dataclass
class DetectedFace:
    """Represents a detected face with biometric features and anti-spoof liveness attributes."""
    bbox: np.ndarray                      # [x1, y1, x2, y2]
    confidence: float                     # Detection confidence 0.0 - 1.0
    landmarks: np.ndarray                 # 5 primary facial landmarks (eyes, nose, mouth)
    landmarks_3d: Optional[np.ndarray] = None  # 68 points (x, y, z) from 1k3d68.onnx
    landmarks_2d: Optional[np.ndarray] = None  # 106 points from 2d106det.onnx
    aligned_face: Optional[np.ndarray] = None  # Aligned face crop (112x112)
    embedding: Optional[np.ndarray] = None     # 512-d normalized ArcFace vector
    quality_score: float = 0.0            # Image clarity & resolution score (0-100)
    
    # 3D Head Pose
    pitch: float = 0.0                    # Vertical head angle in degrees (-ve = up, +ve = down)
    yaw: float = 0.0                      # Horizontal head angle in degrees (-ve = left, +ve = right)
    roll: float = 0.0                     # In-plane rotation in degrees
    pose_label: str = "CENTER"            # 'CENTER', 'LEFT', 'RIGHT', 'TILT_UP', 'TILT_DOWN'
    
    # Anti-Spoofing & Liveness
    ear: float = 0.3                      # Eye Aspect Ratio (blinking < 0.20, open > 0.26)
    depth_z_std: float = 50.0             # 3D depth variance (flat photo < 20.0, real face > 35.0)
    liveness_score: float = 1.0           # 0.0 to 1.0
    is_live: bool = True                  # True if liveness_score >= threshold
    liveness_label: str = "REAL"          # "REAL" or "SPOOF / PHOTO"


def compute_eye_aspect_ratio(eye_landmarks: np.ndarray) -> float:
    """
    Compute Eye Aspect Ratio (EAR) using Soukupová & Čech formula.
    Points: 6 points of one eye ordered counter-clockwise: [p1, p2, p3, p4, p5, p6].
    """
    if eye_landmarks is None or len(eye_landmarks) < 6:
        return 0.3
    p = eye_landmarks
    A = np.linalg.norm(p[1] - p[5])
    B = np.linalg.norm(p[2] - p[4])
    C = np.linalg.norm(p[0] - p[3])
    if C < 1e-4:
        return 0.0
    return float((A + B) / (2.0 * C))


class FaceLivenessTracker:
    """
    Temporal tracker for face liveness over consecutive frames.
    Detects natural eye blinks, 3D facial depth topography, and micro-movements.
    """
    def __init__(self, max_history: int = 15):
        self.max_history = max_history
        # Track history per tracking ID or primary face
        self.ear_history: List[float] = []
        self.pose_history: List[Tuple[float, float, float]] = []
        self.depth_history: List[float] = []
        self.blink_count: int = 0
        self._was_blinking: bool = False

    def update(self, ear: float, pose: Tuple[float, float, float], depth_z_std: float) -> Tuple[float, bool, str]:
        """
        Update temporal history and calculate real-time liveness score.
        
        Returns:
            (liveness_score, is_live, label)
        """
        self.ear_history.append(ear)
        self.pose_history.append(pose)
        self.depth_history.append(depth_z_std)

        if len(self.ear_history) > self.max_history:
            self.ear_history.pop(0)
            self.pose_history.pop(0)
            self.depth_history.pop(0)

        # 1. Blink Detection
        is_blinking = (ear < 0.20)
        if is_blinking and not self._was_blinking:
            self.blink_count += 1
        self._was_blinking = is_blinking

        # 2. 3D Facial Depth Topography Check (Flat photo test)
        # Real 3D head features have significant Z-depth spread from nose tip to ears
        depth_score = min(1.0, max(0.0, (depth_z_std - 18.0) / 32.0))

        # 3. Eye natural aspect ratio & blink test
        ear_var = float(np.std(self.ear_history)) if len(self.ear_history) > 3 else 0.02
        if 0.20 <= ear <= 0.45:
            ear_score = 0.90 + min(0.10, ear_var * 5.0)
        elif ear < 0.20:
            # Currently blinking (active live indicator!)
            ear_score = 1.0
        else:
            ear_score = 0.40

        # 4. Micro-movement & Head Pose Natural Dynamics
        pitch, yaw, roll = pose
        if len(self.pose_history) > 3:
            pitches = [p[0] for p in self.pose_history]
            yaws = [p[1] for p in self.pose_history]
            pose_std = float(np.std(pitches) + np.std(yaws))
            # Human heads always have small natural micro-movements (>0.05 deg)
            motion_score = min(1.0, max(0.2, (pose_std + 0.1) / 0.5))
        else:
            motion_score = 0.85

        # Pose sanity check: Extreme angles (>50 deg) reduce score
        if abs(yaw) > 55 or abs(pitch) > 45:
            pose_penalty = 0.7
        else:
            pose_penalty = 1.0

        # Weighted composite score
        composite = (0.45 * depth_score + 0.35 * ear_score + 0.20 * motion_score) * pose_penalty
        liveness_score = round(float(np.clip(composite, 0.0, 1.0)), 3)

        # Thresholding: 0.65 threshold for genuine live face
        is_live = (liveness_score >= 0.65 and depth_z_std >= 22.0)
        label = "REAL" if is_live else "SPOOF / PHOTO"

        return liveness_score, is_live, label


class FaceDetectionService:
    """
    Production-grade Face Detection, Alignment, 3D Pose & Anti-Spoofing Engine.
    Uses InsightFace (RetinaFace det_10g, ArcFace w600k_r50, 1k3d68, 2d106det).
    """
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._app = None
        self.provider_name = "unavailable"
        self._liveness_trackers: Dict[int, FaceLivenessTracker] = {}
        self._initialized = True
        logger.info("FaceDetectionService instantiated.")

    def load_model(self):
        """Prefer CUDA when usable and fall back to CPU if GPU initialization fails."""
        import src.core.cuda_setup
        import onnxruntime as ort
        from insightface.app import FaceAnalysis

        available = ort.get_available_providers()
        if "CUDAExecutionProvider" in available:
            try:
                self._load_with_provider(FaceAnalysis, "CUDAExecutionProvider")
            except Exception as exc:
                logger.warning(
                    "Could not initialize the CUDA face pipeline ({}); retrying on CPU.",
                    exc,
                )
                self._app = None
                self._load_with_provider(FaceAnalysis, "CPUExecutionProvider")
        else:
            logger.info("CUDA execution provider is unavailable; loading face models on CPU.")
            self._load_with_provider(FaceAnalysis, "CPUExecutionProvider")

        logger.info(f"InsightFace Buffalo_l pipeline loaded with {self.provider_name}.")

    def _load_with_provider(self, face_analysis, provider: str) -> None:
        """Create the InsightFace pipeline with the requested provider and verify its sessions."""
        self._app = face_analysis(
            name="buffalo_l",
            root=settings.model_weights_dir,
            providers=[provider, "CPUExecutionProvider"]
            if provider != "CPUExecutionProvider"
            else [provider],
        )
        self._app.prepare(
            ctx_id=0 if provider == "CUDAExecutionProvider" else -1,
            det_size=(640, 640),
        )
        session_providers = {
            model.session.get_providers()[0]
            for model in self._app.models.values()
            if model.session.get_providers()
        }
        if provider not in session_providers:
            self._app = None
            raise RuntimeError(f"InsightFace did not activate the requested {provider}.")
        self.provider_name = provider

    def detect_and_embed(self, frame: np.ndarray, max_faces: int = 10) -> List[DetectedFace]:
        """
        Execute high-precision detection, 512-d feature extraction, 3D Head Pose,
        and Anti-Spoofing Liveness verification in a single GPU pass.
        """
        if self._app is None:
            raise RuntimeError("InsightFace model not loaded. Call load_model() first.")

        if frame is None or frame.size == 0:
            return []

        raw_faces = self._app.get(frame)
        if not raw_faces:
            return []

        results: List[DetectedFace] = []

        for idx, face in enumerate(raw_faces[:max_faces]):
            det_score = float(face.det_score)
            if det_score < settings.face_detection_threshold:
                continue

            bbox = face.bbox.astype(int)
            x1, y1, x2, y2 = bbox
            h_f, w_f = frame.shape[:2]
            face_w = max(0, x2 - x1)
            face_h = max(0, y2 - y1)

            if face_w < settings.face_quality_min_size or face_h < settings.face_quality_min_size:
                continue

            # Quality calculation
            crop_x1 = max(0, x1)
            crop_y1 = max(0, y1)
            crop_x2 = min(w_f, x2)
            crop_y2 = min(h_f, y2)
            face_crop = frame[crop_y1:crop_y2, crop_x1:crop_x2]
            quality = self._calculate_quality(face_crop) if face_crop.size > 0 else 0.0

            # Normalized 512-d feature embedding vector
            embedding = None
            if face.normed_embedding is not None:
                embedding = face.normed_embedding
            elif face.embedding is not None:
                norm = np.linalg.norm(face.embedding)
                embedding = face.embedding / norm if norm > 1e-6 else None

            # 3D Landmark & Head Pose Analysis
            l3d = face.get("landmark_3d_68")
            l2d = face.get("landmark_2d_106")
            raw_pose = face.get("pose")  # [pitch, yaw, roll] in degrees

            if raw_pose is not None and len(raw_pose) >= 3:
                pitch, yaw, roll = float(raw_pose[0]), float(raw_pose[1]), float(raw_pose[2])
            else:
                pitch, yaw, roll = 0.0, 0.0, 0.0

            # Pose Label classification
            if yaw < -14.0:
                pose_label = "LEFT"
            elif yaw > 14.0:
                pose_label = "RIGHT"
            elif pitch < -18.0:
                pose_label = "TILT_UP"
            elif pitch > 18.0:
                pose_label = "TILT_DOWN"
            else:
                pose_label = "CENTER"

            # Anti-Spoofing / Passive Liveness metrics
            ear = 0.32
            depth_z_std = 50.0

            if l3d is not None and len(l3d) >= 48:
                # 68 landmark indices: left eye 36-41, right eye 42-47
                ear_l = compute_eye_aspect_ratio(l3d[36:42, :2])
                ear_r = compute_eye_aspect_ratio(l3d[42:48, :2])
                ear = (ear_l + ear_r) / 2.0
                depth_z_std = float(np.std(l3d[:, 2]))

            # Update temporal liveness tracker
            tracker = self._liveness_trackers.setdefault(idx, FaceLivenessTracker())
            liveness_score, is_live, liveness_label = tracker.update(ear, (pitch, yaw, roll), depth_z_std)

            results.append(DetectedFace(
                bbox=face.bbox,
                confidence=det_score,
                landmarks=face.kps if face.kps is not None else np.array([]),
                landmarks_3d=l3d,
                landmarks_2d=l2d,
                aligned_face=face_crop,
                embedding=embedding,
                quality_score=quality,
                pitch=pitch,
                yaw=yaw,
                roll=roll,
                pose_label=pose_label,
                ear=ear,
                depth_z_std=depth_z_std,
                liveness_score=liveness_score,
                is_live=is_live,
                liveness_label=liveness_label,
            ))

        # Sort primarily by confidence
        results.sort(key=lambda f: f.confidence, reverse=True)
        return results

    def _calculate_quality(self, face_img: np.ndarray) -> float:
        """Calculate face image quality (clarity, blur Laplacian, illumination) 0-100."""
        if face_img.size == 0:
            return 0.0
        h, w = face_img.shape[:2]
        size_score = min(30.0, (min(h, w) / 112.0) * 30.0)
        gray = cv2.cvtColor(face_img, cv2.COLOR_BGR2GRAY) if len(face_img.shape) == 3 else face_img
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        blur_score = min(40.0, (laplacian_var / 400.0) * 40.0)
        brightness = float(gray.mean())
        if 70.0 <= brightness <= 190.0:
            bright_score = 30.0
        elif brightness < 70.0:
            bright_score = (brightness / 70.0) * 30.0
        else:
            bright_score = max(0.0, ((255.0 - brightness) / 65.0) * 30.0)
        return round(float(size_score + blur_score + bright_score), 1)

    @property
    def is_loaded(self) -> bool:
        return self._app is not None


# Global singleton instance
face_detector = FaceDetectionService()

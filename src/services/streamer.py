"""
High-Throughput Asynchronous Video Pipeline & Biometric Streamer.

Features:
- Decoupled OpenCV Capture & GPU Inference threads via thread-safe Queue.
- Zero-lag frame drop mechanism (never accumulates queue delay on RTSP/Webcam).
- Integrated Liveness Anti-Spoofing verification before attendance triggers.
- FAISS-based 512-d Cosine Similarity matching (<3ms).
- TTL Cache Face Debouncer (configurable 10m cooldown or full-day lock).
- Live HUD bounding box overlays with Liveness Status Badges (REAL / SPOOF).
"""
import os
import cv2
import time
import queue
import threading
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Tuple
import numpy as np

from src.core.config import get_settings
from src.utils.logger import logger
from src.services.face_detection import face_detector, DetectedFace
from src.services.face_matching import face_matcher, MatchResult

settings = get_settings()


class EmployeeSession:
    """Tracks continuous in-frame presence and verification status."""
    def __init__(self, employee_id: int):
        self.employee_id = employee_id
        self.first_seen: float = time.time()
        self.last_seen: float = time.time()
        self.consecutive_frames: int = 0
        self.liveness_passed_frames: int = 0
        self.greeting_sent: bool = False
        self.last_punch_time: float = 0.0
        self.last_punch_type: Optional[str] = None
        self.has_checked_in_today: bool = False
        self.is_late: bool = False
        self.late_minutes: int = 0


class AsyncAttendanceStreamer:
    """
    Decoupled multi-threaded video streaming engine.
    Separates high-framerate camera acquisition from heavy GPU inference.
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

        self.camera_source = 0
        self.cap: Optional[cv2.VideoCapture] = None
        self.is_running = False

        # Decoupled frame queue (maxsize=1 for zero latency)
        self._frame_queue: queue.Queue = queue.Queue(maxsize=1)

        # Thread-safe outputs
        self.latest_raw_frame: Optional[np.ndarray] = None
        self.latest_display_frame: Optional[np.ndarray] = None
        self.latest_jpeg_bytes: Optional[bytes] = None
        
        self.latest_faces: List[DetectedFace] = []
        self.latest_matches: List[Optional[MatchResult]] = []
        self.latest_event_log: List[Dict[str, Any]] = []
        self.latest_recognized_name: Optional[str] = None
        self.latest_greeting_event: Optional[Dict[str, Any]] = None
        self._greeting_event_id = 0

        # Biometric state
        self.sessions: Dict[int, EmployeeSession] = {}
        self.employee_name_cache: Dict[int, str] = {}
        self.employee_code_cache: Dict[int, str] = {}
        self.presence_timeout_seconds: float = 12.0
        self.checked_in_today_ids: set = set()
        self.today_date = datetime.now().date()

        # Telemetry & Performance
        self.fps: float = 0.0
        self._fps_count: int = 0
        self._fps_time: float = time.time()

        self.lock = threading.Lock()
        self.cam_thread: Optional[threading.Thread] = None
        self.ai_thread: Optional[threading.Thread] = None

        self._initialized = True

    def _preload_cache_from_db(self):
        """Preload employee names and today's attendance logs from SQLite."""
        try:
            import sqlite3
            con = sqlite3.connect("data/attendance.db")
            cur = con.cursor()

            # Cache employees
            cur.execute("SELECT id, employee_code, full_name FROM employees WHERE is_active = 1")
            for row in cur.fetchall():
                emp_id, code, name = row
                self.employee_name_cache[emp_id] = name
                self.employee_code_cache[emp_id] = code

            # Cache today's punches
            today_str = datetime.now().strftime("%Y-%m-%d")
            cur.execute("SELECT DISTINCT employee_id FROM attendance_logs WHERE date(timestamp) = ?", (today_str,))
            self.checked_in_today_ids = {r[0] for r in cur.fetchall()}
            self.today_date = datetime.now().date()

            # Preload recent event log for UI feed
            cur.execute("""
                SELECT a.employee_id, e.full_name, e.employee_code, a.event_type, a.timestamp, a.confidence, a.face_image_path, a.liveness_score
                FROM attendance_logs a
                LEFT JOIN employees e ON a.employee_id = e.id
                ORDER BY a.timestamp DESC LIMIT 15
            """)
            recent_rows = cur.fetchall()
            loaded_events = []
            for r in recent_rows:
                emp_id, name, code, ev_type, ts_str, conf, img_path, live_sc = r
                try:
                    dt = datetime.fromisoformat(ts_str) if isinstance(ts_str, str) else ts_str
                    time_s = dt.strftime("%I:%M:%S %p")
                    date_s = dt.strftime("%d %b %Y")
                except Exception:
                    time_s = str(ts_str)
                    date_s = ""

                loaded_events.append({
                    "employee_id": emp_id,
                    "name": name or f"EMP #{emp_id}",
                    "code": code or f"EMP-{emp_id}",
                    "type": ev_type,
                    "time": time_s,
                    "date": date_s,
                    "confidence": round(float(conf or 0.85) * 100, 1),
                    "liveness_score": round(float(live_sc or 1.0) * 100, 1),
                    "snapshot": f"/{img_path.replace(chr(92), '/')}" if img_path else None,
                    "late_desc": "PRESENT",
                    "color": "#10b981",
                })
            self.latest_event_log = loaded_events
            con.close()
            logger.info(f"Loaded {len(self.employee_name_cache)} employees and {len(self.checked_in_today_ids)} punches for today.")
        except Exception as e:
            logger.warning(f"DB cache preload note: {e}")

    def start(self, source=0):
        """Start the decoupled camera ingestion and GPU worker threads."""
        if self.is_running:
            return

        self.camera_source = source
        self.is_running = True
        self._preload_cache_from_db()

        # Start Camera Thread (Fast Capture)
        self.cam_thread = threading.Thread(target=self._camera_capture_worker, daemon=True)
        self.cam_thread.start()

        # Start GPU Inference Worker Thread
        self.ai_thread = threading.Thread(target=self._gpu_inference_worker, daemon=True)
        self.ai_thread.start()

        logger.info(f"AsyncAttendanceStreamer running on source: {source}")

    def stop(self):
        """Stop all background pipelines safely."""
        self.is_running = False
        if self.cam_thread:
            self.cam_thread.join(timeout=2.0)
        if self.ai_thread:
            self.ai_thread.join(timeout=2.0)
        if self.cap and self.cap.isOpened():
            self.cap.release()
        logger.info("AsyncAttendanceStreamer stopped.")

    def remove_employee(self, employee_id: int):
        """Purge memory records when an employee is deleted."""
        with self.lock:
            self.sessions.pop(employee_id, None)
            self.employee_name_cache.pop(employee_id, None)
            self.employee_code_cache.pop(employee_id, None)
            self.checked_in_today_ids.discard(employee_id)
            self.latest_event_log = [e for e in self.latest_event_log if e.get("employee_id") != employee_id]
            face_matcher.debouncer.reset_employee(employee_id)

    def clear_all_data(self):
        """Purge all live kiosk records."""
        with self.lock:
            self.sessions.clear()
            self.employee_name_cache.clear()
            self.employee_code_cache.clear()
            self.checked_in_today_ids.clear()
            self.latest_event_log.clear()
            self.latest_recognized_name = None
            self.latest_greeting_event = None
            face_matcher.debouncer.clear()

    def _camera_capture_worker(self):
        """
        Dedicated capture worker.
        Acquires frames at maximum camera speed, continuously swapping into the 1-frame queue.
        """
        try:
            if isinstance(self.camera_source, int) or (isinstance(self.camera_source, str) and self.camera_source.isdigit()):
                idx = int(self.camera_source)
                self.cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                if not self.cap.isOpened():
                    self.cap = cv2.VideoCapture(idx)
            else:
                os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
                self.cap = cv2.VideoCapture(self.camera_source)

            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            while self.is_running and self.cap.isOpened():
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    time.sleep(0.01)
                    continue

                # Push newest frame to queue; if full, discard oldest for zero latency
                try:
                    self._frame_queue.put_nowait(frame)
                except queue.Full:
                    try:
                        self._frame_queue.get_nowait()
                    except queue.Empty:
                        pass
                    self._frame_queue.put_nowait(frame)

                with self.lock:
                    self.latest_raw_frame = frame
                    self._fps_count += 1

                now = time.time()
                elapsed = now - self._fps_time
                if elapsed >= 1.0:
                    self.fps = self._fps_count / elapsed
                    self._fps_count = 0
                    self._fps_time = now

                time.sleep(0.005)
        except Exception as e:
            logger.error(f"Camera capture worker encountered exception: {e}")
        finally:
            if self.cap and self.cap.isOpened():
                self.cap.release()

    def _gpu_inference_worker(self):
        """
        Dedicated GPU inference worker.
        Runs RetinaFace (det_10g), ArcFace (w600k_r50), 3D Head Pose & EAR Liveness.
        """
        if not face_detector.is_loaded:
            try:
                face_detector.load_model()
            except Exception as exc:
                logger.error(f"Inference disabled: face model could not load: {exc}")
                with self.lock:
                    self.latest_jpeg_bytes = None
                return
        if face_matcher._index is None:
            try:
                face_matcher.initialize()
            except Exception as exc:
                logger.error(f"Inference disabled: face matcher could not initialize: {exc}")
                return

        while self.is_running:
            try:
                frame = self._frame_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                now = time.time()

                # Session timeout cleanup
                expired_ids = [
                    eid for eid, sess in self.sessions.items()
                    if (now - sess.last_seen) > self.presence_timeout_seconds
                ]
                for eid in expired_ids:
                    del self.sessions[eid]

                # Run unified face detection + 3D pose + EAR liveness in one GPU pass
                faces = face_detector.detect_and_embed(frame)
                matches: List[Optional[MatchResult]] = []
                overlays_info = []

                for face in faces:
                    match = None
                    best_match = None
                    if face.embedding is not None:
                        match = face_matcher.identify(face.embedding)
                        # Keep the nearest score for the live diagnostic overlay even when
                        # it is below the recognition threshold. This does not affect matching.
                        if match is None:
                            candidates = face_matcher.search(face.embedding, top_k=1)
                            best_match = candidates[0] if candidates else None
                        else:
                            best_match = match
                    matches.append(match)

                    # Bounding box coordinates
                    bbox = face.bbox.astype(int)
                    x1, y1, x2, y2 = bbox
                    attendance_confidence_min = settings.attendance_detection_confidence_threshold

                    # Greet a live, identity-matched person even if the detection
                    # quality is below the stricter attendance-recording cutoff.
                    # A greeting never lowers the attendance verification threshold.
                    if match and match.is_match and face.is_live:
                        emp_id = match.employee_id
                        disp_name = self.employee_name_cache.get(emp_id, f"EMP #{emp_id}")
                        if emp_id not in self.sessions:
                            self.sessions[emp_id] = EmployeeSession(emp_id)
                        sess = self.sessions[emp_id]
                        if not sess.greeting_sent:
                            sess.greeting_sent = True
                            with self.lock:
                                self.latest_recognized_name = disp_name
                                self._greeting_event_id += 1
                                self.latest_greeting_event = {
                                    "event_id": self._greeting_event_id,
                                    "employee_id": emp_id,
                                    "name": disp_name,
                                    "created_at": time.time(),
                                }
                        if face.confidence < attendance_confidence_min:
                            sess.last_seen = now
                            sess.consecutive_frames = 0
                            sess.liveness_passed_frames = 0

                    # Check match validity
                    # Strict criteria:
                    # 1. Bbox confidence meets the configurable attendance cutoff
                    # 2. Match similarity > 0.60
                    # 3. Liveness check passed (is_live == True & score >= 0.65)
                    if match and match.is_match and face.confidence >= attendance_confidence_min:
                        emp_id = match.employee_id
                        disp_name = self.employee_name_cache.get(emp_id, f"EMP #{emp_id}")
                        emp_code = self.employee_code_cache.get(emp_id, f"EMP-{emp_id}")

                        if emp_id not in self.sessions:
                            self.sessions[emp_id] = EmployeeSession(emp_id)
                        sess = self.sessions[emp_id]
                        sess.last_seen = now
                        if face.is_live:
                            sess.consecutive_frames += 1
                            sess.liveness_passed_frames += 1
                        else:
                            # Require consecutive live frames; a spoof/uncertain frame
                            # resets the verification run instead of inheriting old passes.
                            sess.consecutive_frames = 0
                            sess.liveness_passed_frames = 0

                        # Day rollover check
                        cur_date = datetime.now().date()
                        if cur_date != self.today_date:
                            self.today_date = cur_date
                            self.checked_in_today_ids.clear()

                        # TTL Cooldown & Attendance Verification
                        is_cooldown, remaining_s = face_matcher.debouncer.is_in_cooldown(emp_id)
                        is_already_checked_in = (emp_id in self.checked_in_today_ids)

                        if not face.is_live:
                            liveness_uncertain = face.liveness_score >= 0.55
                            status_title = "LIVE CHECK UNCERTAIN" if liveness_uncertain else "POSSIBLE PHOTO / SPOOF"
                            status_sub = (
                                f"Liveness: {int(face.liveness_score*100)}% (need 65%) | "
                                "Hold still, blink naturally, and face camera. No check-in saved."
                            )
                            overlays_info.append({
                                "bbox": (x1, y1, x2, y2),
                                "title": f"{status_title} ({disp_name})",
                                "sub": status_sub,
                                "status": "LIVENESS_UNCERTAIN" if liveness_uncertain else "POSSIBLE_SPOOF",
                                "color": (0, 165, 255) if liveness_uncertain else (0, 0, 230)
                            })
                        elif is_already_checked_in:
                            overlays_info.append({
                                "bbox": (x1, y1, x2, y2),
                                "title": f"{disp_name} ({emp_code})",
                                "sub": f"Match: {int(match.confidence*100)}% | Checked-In Today [REAL]",
                                "status": "CHECKED_IN",
                                "color": (46, 204, 113)  # Emerald Green
                            })
                        elif is_cooldown:
                            mins_rem = int(remaining_s // 60) + 1
                            overlays_info.append({
                                "bbox": (x1, y1, x2, y2),
                                "title": f"{disp_name} ({emp_code})",
                                "sub": f"Cooldown Active ({mins_rem}m) [REAL]",
                                "status": "COOLDOWN",
                                "color": (52, 152, 219)  # Blue
                            })
                        else:
                            # Candidate for punching attendance
                            overlays_info.append({
                                "bbox": (x1, y1, x2, y2),
                                "title": f"{disp_name} ({emp_code})",
                                "sub": f"Match: {int(match.confidence*100)}% | Liveness: REAL ({int(face.liveness_score*100)}%)",
                                "status": "VERIFYING",
                                "color": (241, 196, 15)  # Gold/Yellow
                            })

                            # Stable frames verification (requires 3 consecutive live frames)
                            if sess.consecutive_frames >= 3 and sess.liveness_passed_frames >= 2:
                                self._trigger_verified_attendance(emp_id, disp_name, emp_code, match.confidence, face, frame)
                    elif match and match.is_match and face.confidence < attendance_confidence_min:
                        disp_name = self.employee_name_cache.get(match.employee_id, f"EMP #{match.employee_id}")
                        if not face.is_live:
                            liveness_uncertain = face.liveness_score >= 0.55
                            status_title = "LIVE CHECK UNCERTAIN" if liveness_uncertain else "POSSIBLE PHOTO / SPOOF"
                            status_sub = f"Liveness: {int(face.liveness_score*100)}% (need 65%) | No check-in saved."
                            box_color = (0, 165, 255) if liveness_uncertain else (0, 0, 230)
                        else:
                            status_title = f"{disp_name} — PAUSE FOR CHECK-IN"
                            status_sub = f"Match: {int(match.confidence*100)}% | Camera: {int(face.confidence*100)}% (need {int(attendance_confidence_min*100)}%) | Stay in view"
                            box_color = (0, 165, 255)
                        overlays_info.append({
                            "bbox": (x1, y1, x2, y2),
                            "title": status_title,
                            "sub": status_sub,
                            "status": "LOW_QUALITY" if face.is_live else "LIVENESS_UNCERTAIN",
                            "color": box_color
                        })
                    else:
                        # Unknown or low confidence face
                        if not face.is_live:
                            liveness_uncertain = face.liveness_score >= 0.55
                            status_title = "LIVE CHECK UNCERTAIN" if liveness_uncertain else "POSSIBLE PHOTO / SPOOF"
                            status_sub = f"Liveness: {int(face.liveness_score*100)}% (need 65%) | Face camera and blink naturally"
                            box_col = (0, 165, 255) if liveness_uncertain else (0, 0, 230)
                        elif best_match is None:
                            status_title = "NO FACE PROFILE"
                            status_sub = f"Liveness: REAL ({int(face.liveness_score*100)}%) | Add employee profile"
                            box_col = (0, 165, 255)
                        else:
                            status_title = "UNKNOWN PERSON"
                            status_sub = f"Best match: {int(best_match.confidence*100)}% (need 60%) | Pose: {face.pose_label}"
                            box_col = (0, 165, 255)  # Orange

                        overlays_info.append({
                            "bbox": (x1, y1, x2, y2),
                            "title": status_title,
                            "sub": status_sub,
                            "status": "UNKNOWN",
                            "color": box_col
                        })

                # Render futuristic HUD overlay on the display frame
                display_frame = self._render_hud_overlay(frame, overlays_info)

                # JPEG encoding
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
                _, jpeg_bytes = cv2.imencode(".jpg", display_frame, encode_param)

                with self.lock:
                    self.latest_display_frame = display_frame
                    self.latest_jpeg_bytes = jpeg_bytes.tobytes()
                    self.latest_faces = faces
                    self.latest_matches = matches

            except Exception as e:
                logger.error(f"Inference worker exception: {e}")

    def _trigger_verified_attendance(self, emp_id: int, name: str, code: str, confidence: float, face: DetectedFace, frame: np.ndarray):
        """Record verified attendance punch into SQLite & Debouncer."""
        now_dt = datetime.now()
        now = time.time()

        # Mark in debouncer and today's checked-in set
        face_matcher.debouncer.record_punch(emp_id, punch_type="CHECK_IN")
        self.checked_in_today_ids.add(emp_id)

        # Shift timing (9:00 AM start with 15 min grace => 9:15 AM)
        shift_cutoff_mins = 9 * 60 + 15
        cur_mins = now_dt.hour * 60 + now_dt.minute
        is_late = (cur_mins > shift_cutoff_mins)
        late_mins = (cur_mins - shift_cutoff_mins) if is_late else 0

        # Save audit face snapshot
        snap_url = None
        snap_rel_path = None
        try:
            os.makedirs("data/snapshots", exist_ok=True)
            snap_name = f"snap_{emp_id}_{int(now)}.jpg"
            snap_abs_path = os.path.join("data", "snapshots", snap_name)
            
            # Crop face with padding
            bbox = face.bbox.astype(int)
            h_f, w_f = frame.shape[:2]
            pad_x = int((bbox[2] - bbox[0]) * 0.35)
            pad_y = int((bbox[3] - bbox[1]) * 0.35)
            x1_c = max(0, bbox[0] - pad_x)
            y1_c = max(0, bbox[1] - pad_y)
            x2_c = min(w_f, bbox[2] + pad_x)
            y2_c = min(h_f, bbox[3] + pad_y)
            face_crop = frame[y1_c:y2_c, x1_c:x2_c]
            cv2.imwrite(snap_abs_path, face_crop)
            
            snap_rel_path = os.path.join("data", "snapshots", snap_name)
            snap_url = f"/data/snapshots/{snap_name}"
        except Exception as e:
            logger.warning(f"Could not write audit snapshot: {e}")

        # Insert record into database synchronously via sqlite3 for instant speed
        try:
            import sqlite3
            con = sqlite3.connect("data/attendance.db")
            cur = con.cursor()
            cur.execute("""
                INSERT INTO attendance_logs (employee_id, camera_id, event_type, timestamp, confidence, liveness_score, anti_spoof_passed, face_image_path, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                emp_id,
                1,
                "CHECK_IN",
                now_dt.strftime("%Y-%m-%d %H:%M:%S"),
                round(float(confidence), 4),
                round(float(face.liveness_score), 4),
                1,
                snap_rel_path,
                '{"kiosk": "main_terminal", "pose": "' + face.pose_label + '", "liveness": "REAL"}'
            ))
            con.commit()
            con.close()
        except Exception as db_err:
            logger.error(f"Error writing attendance log to DB: {db_err}")

        # Update event feed for Web UI
        time_str = now_dt.strftime("%I:%M:%S %p")
        date_str = now_dt.strftime("%d %b %Y")
        late_desc = f"LATE (+{late_mins}m)" if is_late else "ON TIME"
        color = "#eab308" if is_late else "#10b981"

        event_card = {
            "employee_id": emp_id,
            "name": name,
            "code": code,
            "type": "CHECK_IN",
            "time": time_str,
            "date": date_str,
            "confidence": round(confidence * 100, 1),
            "liveness_score": round(face.liveness_score * 100, 1),
            "snapshot": snap_url,
            "late_desc": late_desc,
            "color": color,
        }

        with self.lock:
            self.latest_event_log.insert(0, event_card)
            if len(self.latest_event_log) > 25:
                self.latest_event_log.pop()

        logger.info(f"✅ BIOMETRIC ATTENDANCE RECORDED: {name} ({code}) [{late_desc}] - Confidence: {confidence*100:.1f}%, Liveness: REAL")

    def _render_hud_overlay(self, frame: np.ndarray, overlays: List[Dict[str, Any]]) -> np.ndarray:
        """Render high-tech cyber-biometric bounding boxes & badges onto video."""
        out = frame.copy()
        h, w = out.shape[:2]

        for item in overlays:
            x1, y1, x2, y2 = item["bbox"]
            color = item["color"]
            title = item["title"]
            sub = item["sub"]

            # Draw sleek corner bracket bounding box
            corner_len = min(25, (x2 - x1) // 4)
            t = 2

            # Corners
            cv2.line(out, (x1, y1), (x1 + corner_len, y1), color, t)
            cv2.line(out, (x1, y1), (x1, y1 + corner_len), color, t)
            cv2.line(out, (x2, y1), (x2 - corner_len, y1), color, t)
            cv2.line(out, (x2, y1), (x2, y1 + corner_len), color, t)
            cv2.line(out, (x1, y2), (x1 + corner_len, y2), color, t)
            cv2.line(out, (x1, y2), (x1, y2 - corner_len), color, t)
            cv2.line(out, (x2, y2), (x2 - corner_len, y2), color, t)
            cv2.line(out, (x2, y2), (x2, y2 - corner_len), color, t)

            # Translucent badge background for text
            tag_y1 = max(0, y1 - 42)
            tag_y2 = y1
            tag_x1 = x1
            tag_x2 = min(w, x1 + max(len(title), len(sub)) * 9 + 20)

            # Draw pill background
            cv2.rectangle(out, (tag_x1, tag_y1), (tag_x2, tag_y2), (15, 23, 42), -1)
            cv2.rectangle(out, (tag_x1, tag_y1), (tag_x2, tag_y2), color, 1)

            # Text
            cv2.putText(out, title, (tag_x1 + 6, tag_y1 + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.putText(out, sub, (tag_x1 + 6, tag_y1 + 34), cv2.FONT_HERSHEY_SIMPLEX, 0.40, color, 1, cv2.LINE_AA)

        return out

    def get_latest_jpeg(self) -> Optional[bytes]:
        """Thread-safe retrieval of latest compressed frame bytes."""
        with self.lock:
            return self.latest_jpeg_bytes

    def capture_high_res_face(self) -> Optional[np.ndarray]:
        """Grab a fresh uncompressed frame for enrollment or high-precision scanning."""
        with self.lock:
            if self.latest_raw_frame is not None:
                return self.latest_raw_frame.copy()
            return None

    def get_telemetry(self) -> Dict[str, Any]:
        """Live telemetry payload for WebSocket / polling clients."""
        with self.lock:
            active_events = list(self.latest_event_log)
            # The HTTP status poll consumes this one-shot event. WebSocket telemetry
            # only observes it so it cannot race the UI's greeting poll.
            rec_name = self.latest_recognized_name
            greeting_event = self.latest_greeting_event

            camera_active = self.is_running and self.latest_jpeg_bytes is not None

        return {
            "fps": round(self.fps, 1) if camera_active else 0.0,
            "camera_active": camera_active,
            "checked_in_today_count": len(self.checked_in_today_ids),
            "latest_recognized": rec_name,
            "greeting_event": greeting_event,
            "recent_events": active_events,
        }


# Global singleton streamer
streamer = AsyncAttendanceStreamer()

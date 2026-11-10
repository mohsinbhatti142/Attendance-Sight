"""
Employee Face Registration Script.

Captures face images from laptop webcam or USB camera and enrolls an employee.

Usage:
    python -m scripts.register_employee --code EMP001 --name "Ali Khan"
"""
import os
import sys
import argparse
import cv2
import numpy as np
from datetime import datetime

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import src.core.cuda_setup

from src.core.config import get_settings
from src.utils.logger import logger, setup_logger
from src.services.face_detection import face_detector
from src.services.face_matching import face_matcher
from src.utils.image_utils import save_face_image

settings = get_settings()


def capture_faces(num_captures: int = 5, camera_idx: int = 0) -> list:
    """Capture multiple face images from camera."""
    cap = cv2.VideoCapture(camera_idx, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(camera_idx)
    
    if not cap.isOpened():
        print(f"❌ Error: Camera (index {camera_idx}) could not be opened! Make sure no other app (like Zoom/Teams) is using the camera.")
        return []
    
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    
    captured = []
    
    print("\n" + "=" * 50)
    print("📷 Camera started! Look straight at the camera.")
    print("Press [SPACEBAR] to capture each sample.")
    print("Press [Q] to quit/finish early.")
    print("=" * 50 + "\n")
    
    while len(captured) < num_captures:
        ret, frame = cap.read()
        if not ret:
            print("Warning: Could not read frame from camera.")
            continue
        
        # Real-time face detection on preview
        faces = face_detector.detect_and_embed(frame)
        
        display = frame.copy()
        face_status = "No Face"
        status_color = (0, 0, 255)
        
        for face in faces:
            bbox = face.bbox.astype(int)
            cv2.rectangle(display, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 255, 0), 2)
            face_status = f"Face OK (Quality: {face.quality_score:.0f}%)"
            status_color = (0, 255, 0)
            
            # Show facial landmarks
            if face.landmarks is not None and len(face.landmarks) > 0:
                for pt in face.landmarks:
                    cv2.circle(display, (int(pt[0]), int(pt[1])), 2, (0, 255, 255), -1)
        
        # UI Overlays
        cv2.putText(
            display,
            f"Progress: {len(captured)}/{num_captures} captures",
            (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2
        )
        cv2.putText(
            display,
            f"Status: {face_status}",
            (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_color, 2
        )
        cv2.putText(
            display,
            "Press [SPACE] to capture | [Q] to finish",
            (20, display.shape[0] - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1
        )
        
        cv2.imshow("Employee Face Enrollment", display)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord(' ') and faces:
            best_face = faces[0]
            captured.append((frame.copy(), best_face))
            print(f"  ✅ Captured {len(captured)}/{num_captures} (Confidence: {best_face.confidence:.2f}, Quality: {best_face.quality_score:.1f})")
        elif key == ord('q'):
            break
    
    cap.release()
    cv2.destroyAllWindows()
    return captured


def main():
    parser = argparse.ArgumentParser(description="Register Employee Face")
    parser.add_argument("--code", required=True, help="Employee code (e.g., EMP001)")
    parser.add_argument("--name", required=True, help="Employee full name")
    parser.add_argument("--camera", type=int, default=0, help="Camera index (default 0 for laptop webcam)")
    parser.add_argument("--captures", type=int, default=5, help="Number of face captures")
    args = parser.parse_args()
    
    setup_logger()
    
    print("\n" + "=" * 55)
    print(f"  Registering: {args.name} (Code: {args.code})")
    print("=" * 55)
    
    print("🧠 Loading Face Recognition Model (InsightFace / ArcFace)...")
    face_detector.load_model()
    face_matcher.initialize()
    print("✅ Model loaded successfully!")
    
    captures = capture_faces(num_captures=args.captures, camera_idx=args.camera)
    
    if not captures:
        print("❌ No images captured. Registration cancelled.")
        return
    
    print(f"\n💾 Processing {len(captures)} face embeddings...")
    emp_id = abs(hash(args.code)) % 100000
    
    for i, (frame, face) in enumerate(captures):
        if face.embedding is not None:
            face_matcher.add_embedding(emp_id, face.embedding)
            save_face_image(frame, emp_id, settings.face_images_dir)
            print(f"  ✅ Sample {i+1} saved to index.")
    
    face_matcher.save_index()
    
    print("\n" + "=" * 55)
    print("🎉 REGISTRATION COMPLETE!")
    print(f"   Name:       {args.name}")
    print(f"   Code:       {args.code}")
    print(f"   ID:         {emp_id}")
    print(f"   Samples:    {len(captures)}")
    print(f"   Total DB:   {face_matcher.total_embeddings} face vectors")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()

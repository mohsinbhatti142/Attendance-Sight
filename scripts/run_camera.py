"""
Real-time Face Detection & Attendance from Camera (GPU Accelerated & Async).

Uses asynchronous background GPU worker thread so the camera display runs
at a smooth 30-60 FPS without any stutter or lag.

Usage:
    python -m scripts.run_camera                        # Laptop webcam
    python -m scripts.run_camera --source 0             # Default webcam
    python -m scripts.run_camera --source "rtsp://..."  # CCTV IP Camera
"""
import os
import sys
import argparse
import time
import cv2

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import src.core.cuda_setup

from src.core.config import get_settings
from src.utils.logger import logger, setup_logger
from src.services.streamer import streamer

settings = get_settings()


def main():
    parser = argparse.ArgumentParser(description="Real-time Face Attendance")
    parser.add_argument("--source", default="0", help="Camera source (0 for webcam, or RTSP URL for CCTV)")
    args = parser.parse_args()

    setup_logger()
    print("\n" + "=" * 60)
    print("🚀 Starting GPU-Accelerated Attendance Streamer...")
    print(f"   Camera: {args.source}")
    print("   GPU: NVIDIA Quadro P5000 (CUDA Execution Provider)")
    print("=" * 60 + "\n")

    parsed_source = int(args.source) if str(args.source).isdigit() else args.source
    streamer.start(source=parsed_source)

    print("📷 Camera Feed Active! Press [Q] to quit window.\n")

    try:
        while streamer.is_running:
            with streamer.lock:
                frame = streamer.latest_display_frame if streamer.latest_display_frame is not None else streamer.latest_raw_frame

            if frame is not None:
                cv2.imshow("Attendance-Sight Face Recognition", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break

            time.sleep(0.01)  # Smooth 60 FPS refresh
    except KeyboardInterrupt:
        pass
    finally:
        streamer.stop()
        cv2.destroyAllWindows()
        print("\n👋 Attendance system stopped safely.")


if __name__ == "__main__":
    main()

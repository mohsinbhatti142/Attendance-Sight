"""Image processing utility functions for face detection and recognition."""

import base64
import os
import uuid
from pathlib import Path

import cv2
import numpy as np


def encode_image_to_base64(image: np.ndarray) -> str:
    """Encode a BGR numpy image to a base64-encoded JPEG string.

    Args:
        image: BGR image as a numpy array (H, W, C).

    Returns:
        Base64-encoded string of the JPEG image.

    Raises:
        ValueError: If the image encoding fails.
    """
    success, buffer = cv2.imencode(".jpg", image)
    if not success:
        raise ValueError("Failed to encode image to JPEG.")
    return base64.b64encode(buffer).decode("utf-8")


def decode_base64_to_image(base64_str: str) -> np.ndarray:
    """Decode a base64-encoded string back to a BGR numpy image.

    Args:
        base64_str: Base64-encoded image string (JPEG or PNG).

    Returns:
        BGR image as a numpy array (H, W, C).

    Raises:
        ValueError: If the base64 string cannot be decoded into a valid image.
    """
    img_bytes = base64.b64decode(base64_str)
    img_array = np.frombuffer(img_bytes, dtype=np.uint8)
    image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Failed to decode base64 string into a valid image.")
    return image


def resize_image(image: np.ndarray, max_size: int = 640) -> np.ndarray:
    """Resize an image so its longest side does not exceed *max_size*.

    Aspect ratio is preserved.  If the image is already within bounds it is
    returned unchanged.

    Args:
        image: BGR image as a numpy array (H, W, C).
        max_size: Maximum allowed dimension (width or height).

    Returns:
        Resized BGR image as a numpy array.
    """
    h, w = image.shape[:2]
    if max(h, w) <= max_size:
        return image

    scale = max_size / max(h, w)
    new_w = int(w * scale)
    new_h = int(h * scale)
    return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)


def calculate_blur_score(image: np.ndarray) -> float:
    """Calculate a sharpness score using the variance of the Laplacian.

    Higher values indicate a sharper (less blurry) image.

    Args:
        image: BGR image as a numpy array (H, W, C).

    Returns:
        Blur score (variance of the Laplacian).
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def is_face_quality_ok(
    face_img: np.ndarray,
    min_size: int = 80,
    min_blur_score: float = 50.0,
) -> tuple[bool, str]:
    """Check whether a cropped face image meets minimum quality requirements.

    Args:
        face_img: Cropped face image as a numpy array (H, W, C).
        min_size: Minimum width and height in pixels.
        min_blur_score: Minimum Laplacian variance (sharpness threshold).

    Returns:
        A tuple of (is_ok, reason).
        *is_ok* is True when quality is acceptable; *reason* provides detail
        when it is not.
    """
    h, w = face_img.shape[:2]

    if w < min_size or h < min_size:
        return False, (
            f"Face image too small ({w}x{h}). "
            f"Minimum required size is {min_size}x{min_size}."
        )

    blur = calculate_blur_score(face_img)
    if blur < min_blur_score:
        return False, (
            f"Face image too blurry (score={blur:.1f}). "
            f"Minimum required score is {min_blur_score:.1f}."
        )

    return True, "Quality OK."


def save_face_image(
    image: np.ndarray,
    employee_id: int,
    base_dir: str = "data/face_images",
) -> str:
    """Save a face image to disk organised by employee ID.

    Images are stored as ``<base_dir>/<employee_id>/<uuid>.jpg``.

    Args:
        image: BGR face image as a numpy array (H, W, C).
        employee_id: Unique identifier of the employee.
        base_dir: Root directory for face image storage.

    Returns:
        The file path (relative to the project root) of the saved image.

    Raises:
        IOError: If the image cannot be written to disk.
    """
    save_dir = Path(base_dir) / str(employee_id)
    save_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid.uuid4()}.jpg"
    filepath = save_dir / filename

    success = cv2.imwrite(str(filepath), image)
    if not success:
        raise IOError(f"Failed to save face image to {filepath}")

    return str(filepath)


def align_face(image: np.ndarray, landmarks: np.ndarray) -> np.ndarray:
    """Align a face image using an affine transform on 5 facial landmarks.

    The five landmarks are expected in the standard order:
    left_eye, right_eye, nose, left_mouth, right_mouth.

    Args:
        image: BGR image as a numpy array (H, W, C).
        landmarks: Array of shape (5, 2) with (x, y) coordinates for the
            five facial landmarks.

    Returns:
        Aligned face image cropped to 112×112 pixels (ArcFace standard).
    """
    # Standard destination landmarks for a 112×112 aligned face (ArcFace)
    dst_landmarks = np.array(
        [
            [38.2946, 51.6963],
            [73.5318, 51.5014],
            [56.0252, 71.7366],
            [41.5493, 92.3655],
            [70.7299, 92.2041],
        ],
        dtype=np.float32,
    )

    src_pts = np.float32(landmarks[:3])
    dst_pts = np.float32(dst_landmarks[:3])

    affine_mat = cv2.getAffineTransform(src_pts, dst_pts)
    aligned = cv2.warpAffine(
        image,
        affine_mat,
        (112, 112),
        borderMode=cv2.BORDER_REPLICATE,
    )
    return aligned

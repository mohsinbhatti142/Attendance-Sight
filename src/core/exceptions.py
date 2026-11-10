"""Custom exception classes for the Face Detection Attendance System."""


class FaceDetectionError(Exception):
    """Base exception for all face-detection related errors."""

    def __init__(self, message: str = "A face detection error occurred.") -> None:
        self.message = message
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


class FaceNotFoundError(FaceDetectionError):
    """Raised when no face is detected in the provided image."""

    def __init__(self, message: str = "No face detected in the provided image.") -> None:
        super().__init__(message)


class EmployeeNotFoundError(FaceDetectionError):
    """Raised when an employee cannot be found in the database."""

    def __init__(self, message: str = "Employee not found.") -> None:
        super().__init__(message)


class DuplicateEmployeeError(FaceDetectionError):
    """Raised when attempting to register an employee that already exists."""

    def __init__(self, message: str = "Employee already exists.") -> None:
        super().__init__(message)


class CameraConnectionError(FaceDetectionError):
    """Raised when a camera connection fails or is unavailable."""

    def __init__(self, message: str = "Failed to connect to camera.") -> None:
        super().__init__(message)


class LowQualityFaceError(FaceDetectionError):
    """Raised when the detected face image quality is too low for recognition."""

    def __init__(self, message: str = "Face image quality is too low.") -> None:
        super().__init__(message)


class FaceMatchError(FaceDetectionError):
    """Raised when face matching/comparison fails or produces no match."""

    def __init__(self, message: str = "Face matching failed.") -> None:
        super().__init__(message)

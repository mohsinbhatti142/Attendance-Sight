"""Application configuration using pydantic-settings."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────
    app_name: str = "Attendance-Sight"
    app_env: str = "development"
    app_debug: bool = True
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    local_demo_mode: bool = False
    secret_key: str = "your-secret-key-change-this"
    email_credentials_file: str = "data/email_sender.enc"

    # ── Database ─────────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./data/attendance.db"
    database_echo: bool = False

    # ── Redis ────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Face Recognition ─────────────────────────────────────────────────
    face_detection_model: str = "retinaface_r50"
    face_recognition_model: str = "arcface_r100"
    face_detection_threshold: float = 0.5
    face_recognition_threshold: float = 0.6
    attendance_detection_confidence_threshold: float = 0.75
    face_quality_min_size: int = 80
    max_faces_per_frame: int = 10

    # ── Camera ───────────────────────────────────────────────────────────
    frame_skip: int = 3
    camera_resolution_width: int = 1280
    camera_resolution_height: int = 720

    # ── Storage ──────────────────────────────────────────────────────────
    face_images_dir: str = "data/face_images"
    model_weights_dir: str = "data/models"
    faiss_index_dir: str = "data/faiss_index"

    # ── CORS ─────────────────────────────────────────────────────────────
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
    ]

    # ── Logging ──────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_file: str = "logs/app.log"

    # ── Computed Properties ──────────────────────────────────────────────
    @property
    def sync_database_url(self) -> str:
        """Return a synchronous database URL (for Alembic migrations, etc.)."""
        return self.database_url.replace(
            "postgresql+asyncpg://", "postgresql+psycopg2://"
        )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> list[str]:
        """Accept both a JSON-encoded string and a Python list."""
        if isinstance(v, str):
            import json

            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [origin.strip() for origin in v.split(",")]
        return v  # type: ignore[return-value]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (singleton)."""
    return Settings()

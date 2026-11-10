"""Database models for the Face Attendance System."""
import enum
from datetime import datetime, date
from typing import Optional, List

from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, Date, Text,
    ForeignKey, Enum, LargeBinary, JSON, Index, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.db.database import Base


class EventType(str, enum.Enum):
    CHECK_IN = "CHECK_IN"
    CHECK_OUT = "CHECK_OUT"


class LeaveStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class CameraType(str, enum.Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    BOTH = "BOTH"


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    employees: Mapped[List["Employee"]] = relationship("Employee", back_populates="department", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Department(id={self.id}, name={self.name})>"


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    department_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("departments.id"), nullable=True)
    designation: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    joining_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    profile_image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    department: Mapped[Optional["Department"]] = relationship("Department", back_populates="employees", lazy="selectin")
    face_encodings: Mapped[List["FaceEncoding"]] = relationship("FaceEncoding", back_populates="employee", lazy="selectin", cascade="all, delete-orphan")
    attendance_logs: Mapped[List["AttendanceLog"]] = relationship("AttendanceLog", back_populates="employee", lazy="noload")

    def __repr__(self) -> str:
        return f"<Employee(id={self.id}, code={self.employee_code}, name={self.full_name})>"


class FaceEncoding(Base):
    __tablename__ = "face_encodings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)  # numpy array serialized
    image_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pose_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default="CENTER")  # CENTER, LEFT, RIGHT, TILT_UP, TILT_DOWN
    liveness_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=1.0)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    employee: Mapped["Employee"] = relationship("Employee", back_populates="face_encodings")

    def __repr__(self) -> str:
        return f"<FaceEncoding(id={self.id}, employee_id={self.employee_id}, pose={self.pose_type})>"


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(String(500), nullable=False)  # RTSP URL or camera index "0"
    camera_type: Mapped[CameraType] = mapped_column(Enum(CameraType), default=CameraType.BOTH)
    location: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    attendance_logs: Mapped[List["AttendanceLog"]] = relationship("AttendanceLog", back_populates="camera", lazy="noload")

    def __repr__(self) -> str:
        return f"<Camera(id={self.id}, name={self.name})>"


class AttendanceLog(Base):
    __tablename__ = "attendance_logs"
    __table_args__ = (
        Index("idx_attendance_employee_date", "employee_id", "timestamp"),
        Index("idx_attendance_timestamp", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(Integer, ForeignKey("employees.id"), nullable=False)
    camera_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("cameras.id"), nullable=True)
    event_type: Mapped[EventType] = mapped_column(Enum(EventType), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    liveness_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=1.0)
    anti_spoof_passed: Mapped[bool] = mapped_column(Boolean, default=True)
    face_image_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    employee: Mapped["Employee"] = relationship("Employee", back_populates="attendance_logs", lazy="selectin")
    camera: Mapped[Optional["Camera"]] = relationship("Camera", back_populates="attendance_logs", lazy="selectin")

    def __repr__(self) -> str:
        return f"<AttendanceLog(id={self.id}, employee={self.employee_id}, type={self.event_type})>"


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    session_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<AdminUser(id={self.id}, username={self.username})>"


class EmailVerificationCode(Base):
    __tablename__ = "email_verification_codes"
    __table_args__ = (UniqueConstraint("email", "purpose"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ShiftPolicy(Base):
    """Administrator-managed rules used to classify attendance."""
    __tablename__ = "shift_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, default="Standard shift")
    start_time: Mapped[str] = mapped_column(String(5), nullable=False, default="09:00")
    end_time: Mapped[str] = mapped_column(String(5), nullable=False, default="18:00")
    grace_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    work_days: Mapped[list] = mapped_column(JSON, nullable=False, default=lambda: [0, 1, 2, 3, 4])
    half_day_hours: Mapped[float] = mapped_column(Float, nullable=False, default=4.0)
    overtime_after_hours: Mapped[float] = mapped_column(Float, nullable=False, default=9.0)
    overtime_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=1.5)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

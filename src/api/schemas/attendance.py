"""Pydantic schemas for Attendance endpoints."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AttendanceLogResponse(BaseModel):
    """Schema for a single attendance log entry."""
    id: int
    employee_id: int
    employee_name: str
    event_type: str
    timestamp: datetime
    confidence: float
    camera_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AttendanceSummary(BaseModel):
    """Summary of an employee's attendance for a given day."""
    employee_id: int
    employee_name: str
    employee_code: str
    check_in: Optional[datetime] = None
    check_out: Optional[datetime] = None
    status: str = Field(..., description="PRESENT | ABSENT | LATE | HALF_DAY")
    work_hours: Optional[float] = None


class DailyAttendanceReport(BaseModel):
    """Aggregated attendance report for a single day."""
    date: date
    total_employees: int
    present: int
    absent: int
    late: int
    records: list[AttendanceSummary]


class ManualAttendanceRequest(BaseModel):
    """Schema for manually recording an attendance event."""
    employee_id: int
    event_type: str = Field(..., description="CHECK_IN or CHECK_OUT")
    timestamp: Optional[datetime] = None

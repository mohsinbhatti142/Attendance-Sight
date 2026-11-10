"""Pydantic schemas for Employee endpoints."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class EmployeeBase(BaseModel):
    """Base schema for Employee data."""
    employee_code: str = Field(..., min_length=1, max_length=50, description="Unique employee code")
    full_name: str = Field(..., min_length=1, max_length=200, description="Full name of the employee")
    email: Optional[str] = Field(None, max_length=255, description="Email address")
    phone: Optional[str] = Field(None, max_length=20, description="Phone number")
    department_id: Optional[int] = Field(None, description="Department ID")
    designation: Optional[str] = Field(None, max_length=100, description="Job designation")
    joining_date: Optional[date] = Field(None, description="Date of joining")


class EmployeeCreate(EmployeeBase):
    """Schema for creating a new employee."""
    pass


class EmployeeUpdate(BaseModel):
    """Schema for updating an employee. All fields are optional."""
    employee_code: Optional[str] = Field(None, min_length=1, max_length=50)
    full_name: Optional[str] = Field(None, min_length=1, max_length=200)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    department_id: Optional[int] = None
    designation: Optional[str] = Field(None, max_length=100)
    joining_date: Optional[date] = None
    is_active: Optional[bool] = None


class EmployeeResponse(EmployeeBase):
    """Schema for employee response."""
    id: int
    is_active: bool
    profile_image_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmployeeListResponse(BaseModel):
    """Schema for paginated employee list response."""
    employees: list[EmployeeResponse]
    total: int

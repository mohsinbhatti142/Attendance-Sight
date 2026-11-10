"""Attendance API routes."""
from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_db
from src.db.models import AttendanceLog, Employee, EventType, ShiftPolicy
from src.api.schemas.attendance import (
    DailyAttendanceReport, ManualAttendanceRequest
)
from src.services.attendance import attendance_service
from src.utils.logger import logger
from src.api.deps import require_admin

router = APIRouter(prefix="/attendance", tags=["Attendance"], dependencies=[Depends(require_admin)])


async def _active_policy(db: AsyncSession):
    policy = await db.scalar(select(ShiftPolicy).where(ShiftPolicy.is_active.is_(True)).order_by(ShiftPolicy.id).limit(1))
    return policy


@router.get("/shift_policy")
async def get_shift_policy(db: AsyncSession = Depends(get_db)):
    policy = await _active_policy(db)
    if not policy:
        return {
            "id": None,
            "name": "Standard shift",
            "start_time": "09:00",
            "end_time": "18:00",
            "grace_minutes": 15,
            "work_days": [0, 1, 2, 3, 4],
            "half_day_hours": 4.0,
            "overtime_after_hours": 9.0,
            "overtime_multiplier": 1.5,
            "configured": False,
        }
    return {"id": policy.id, "name": policy.name, "start_time": policy.start_time, "end_time": policy.end_time,
            "grace_minutes": policy.grace_minutes, "work_days": policy.work_days,
            "half_day_hours": policy.half_day_hours, "overtime_after_hours": policy.overtime_after_hours,
            "overtime_multiplier": policy.overtime_multiplier, "configured": True}


@router.put("/shift_policy")
async def save_shift_policy(body: dict, db: AsyncSession = Depends(get_db)):
    from pydantic import BaseModel, Field, ValidationError
    class PolicyInput(BaseModel):
        name: str = Field(min_length=2, max_length=100)
        start_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
        end_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
        grace_minutes: int = Field(ge=0, le=240)
        work_days: list[int] = Field(min_length=1, max_length=7)
        half_day_hours: float = Field(gt=0, le=24)
        overtime_after_hours: float = Field(gt=0, le=24)
        overtime_multiplier: float = Field(ge=1, le=5)
    try:
        values = PolicyInput.model_validate(body).model_dump()
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    if any(day not in range(7) for day in values["work_days"]):
        raise HTTPException(status_code=422, detail="Work days must be weekday numbers from 0 to 6")
    if values["end_time"] <= values["start_time"]:
        raise HTTPException(status_code=422, detail="End time must be later than start time")
    policy = await _active_policy(db)
    if policy is None:
        policy = ShiftPolicy()
        db.add(policy)
    for key, value in values.items():
        setattr(policy, key, value)
    await db.flush()
    return {"saved": True, "id": policy.id, "configured": True, **values}


@router.get("/daily_archive")
async def get_daily_archive(year: int | None = None, month: int | None = None, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import func
    stmt = select(func.date(AttendanceLog.timestamp).label("day"), func.count(AttendanceLog.id).label("events"),
                  func.count(func.distinct(AttendanceLog.employee_id)).label("employees")).group_by(func.date(AttendanceLog.timestamp)).order_by(func.date(AttendanceLog.timestamp).desc())
    if month is not None:
        if month < 1 or month > 12:
            raise HTTPException(status_code=422, detail="Month must be 1–12")
    archive_year = year or date.today().year
    first_day = date(archive_year, month or 1, 1)
    if month is None:
        next_period = date(archive_year + 1, 1, 1)
    elif month == 12:
        next_period = date(archive_year + 1, 1, 1)
    else:
        next_period = date(archive_year, month + 1, 1)
    stmt = stmt.where(
        AttendanceLog.timestamp >= datetime.combine(first_day, time.min),
        AttendanceLog.timestamp < datetime.combine(next_period, time.min),
    )
    rows = (await db.execute(stmt)).all()
    return [{"date": str(row.day), "events": row.events, "employees": row.employees} for row in rows]


@router.get("/day/{day}")
async def get_daily_records(day: date, db: AsyncSession = Depends(get_db)):
    start = datetime.combine(day, time.min); end = start + timedelta(days=1)
    rows = (await db.execute(select(AttendanceLog, Employee).join(Employee).where(AttendanceLog.timestamp >= start, AttendanceLog.timestamp < end).order_by(Employee.full_name, AttendanceLog.timestamp))).all()
    policy = await _active_policy(db)
    grace = int(policy.grace_minutes if policy else 15)
    shift_start = time.fromisoformat(policy.start_time if policy else "09:00")
    grouped = {}
    for log, employee in rows:
        item = grouped.setdefault(employee.id, {"employee_id": employee.id, "employee_name": employee.full_name, "employee_code": employee.employee_code, "department": employee.department.name if employee.department else "General", "check_in": None, "check_out": None, "hours": 0.0, "late": False, "late_minutes": 0, "events": []})
        if log.event_type == EventType.CHECK_IN and item["check_in"] is None:
            item["check_in"] = log.timestamp.isoformat()
            start_minutes = shift_start.hour * 60 + shift_start.minute
            arrived = log.timestamp.hour * 60 + log.timestamp.minute
            item["late_minutes"] = max(0, arrived - start_minutes - grace)
            item["late"] = item["late_minutes"] > 0
        if log.event_type == EventType.CHECK_OUT:
            item["check_out"] = log.timestamp.isoformat()
            if item["check_in"]:
                item["hours"] = round((log.timestamp - datetime.fromisoformat(item["check_in"])).total_seconds() / 3600, 2)
                item["half_day"] = item["hours"] < float(policy.half_day_hours if policy else 4.0)
        item["events"].append({"type": log.event_type.value, "time": log.timestamp.isoformat(), "image": f"/api/v1/audit-images/{log.id}" if log.face_image_path else None})
    emps = (await db.execute(select(Employee).where(Employee.is_active.is_(True)))).scalars().all()
    for employee in emps:
        grouped.setdefault(employee.id, {"employee_id": employee.id, "employee_name": employee.full_name, "employee_code": employee.employee_code, "department": employee.department.name if employee.department else "General", "check_in": None, "check_out": None, "hours": 0.0, "late": False, "half_day": False, "late_minutes": 0, "events": []})
    return {"date": day.isoformat(), "records": sorted(grouped.values(), key=lambda row: row["employee_name"].lower())}


@router.get("/today")
async def get_today_attendance(db: AsyncSession = Depends(get_db)):
    """Get today's attendance summary for all employees."""
    summary = await attendance_service.get_today_summary(db)
    return summary


@router.get("/dashboard_kpis")
async def get_dashboard_kpis(db: AsyncSession = Depends(get_db)):
    """Live KPI counters and department attendance distribution for Dashboard."""
    from datetime import date, datetime, time
    from sqlalchemy.orm import joinedload
    from sqlalchemy import and_

    today_start = datetime.combine(date.today(), time.min)

    # 1. Active Employees
    emp_res = await db.execute(
        select(Employee).options(joinedload(Employee.department)).where(Employee.is_active == True)
    )
    employees = emp_res.scalars().all()
    total_workforce = len(employees)
    active_emp_ids = set(e.id for e in employees)

    if total_workforce == 0:
        return {
            "total_workforce": 0,
            "present_today": 0,
            "late_arrivals": 0,
            "absent_today": 0,
            "attendance_rate": 0.0,
            "departments": [],
        }

    # 2. Today's check-ins
    today_logs_res = await db.execute(
        select(AttendanceLog).where(
            and_(
                AttendanceLog.timestamp >= today_start,
                AttendanceLog.employee_id.in_(active_emp_ids)
            )
        ).order_by(AttendanceLog.timestamp)
    )
    today_logs = today_logs_res.scalars().all()

    policy = await _active_policy(db)
    shift_start = time.fromisoformat(policy.start_time if policy else "09:00")
    grace_minutes = int(policy.grace_minutes if policy else 15)
    late_after = (shift_start.hour * 60 + shift_start.minute + grace_minutes)
    present_emp_ids = set()
    late_emp_ids = set()

    for l in today_logs:
        if l.event_type == EventType.CHECK_IN:
            if l.employee_id not in present_emp_ids:
                present_emp_ids.add(l.employee_id)
                if l.timestamp.hour * 60 + l.timestamp.minute > late_after:
                    late_emp_ids.add(l.employee_id)

    present_today = len(present_emp_ids)
    late_arrivals = len(late_emp_ids)
    absent_today = max(0, total_workforce - present_today)
    att_rate = round((present_today / total_workforce) * 100.0, 1) if total_workforce > 0 else 0.0

    # 3. Department Breakdown
    dept_map = {}
    for e in employees:
        dept_name = e.department.name if e.department else "General"
        if dept_name not in dept_map:
            dept_map[dept_name] = {"total": 0, "present": 0}
        dept_map[dept_name]["total"] += 1
        if e.id in present_emp_ids:
            dept_map[dept_name]["present"] += 1

    departments_list = [
        {
            "name": d_name,
            "total": d_val["total"],
            "present": d_val["present"],
            "pct": round((d_val["present"] / d_val["total"]) * 100.0, 1) if d_val["total"] > 0 else 0.0
        }
        for d_name, d_val in dept_map.items()
    ]

    return {
        "total_workforce": total_workforce,
        "present_today": present_today,
        "late_arrivals": late_arrivals,
        "absent_today": absent_today,
        "attendance_rate": att_rate,
        "departments": departments_list,
    }


def _to_web_path(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    norm = path.replace("\\", "/")
    return norm if norm.startswith("/") else f"/{norm}"


@router.get("/employee_card/{employee_id}")
async def get_employee_attendance_card(
    employee_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Retrieve full biometric attendance identity card and recent punch log for an employee."""
    from src.db.models import FaceEncoding
    from datetime import date, datetime, time, timedelta

    emp_res = await db.execute(select(Employee).where(Employee.id == employee_id))
    employee = emp_res.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Get primary face photo
    face_res = await db.execute(
        select(FaceEncoding).where(FaceEncoding.employee_id == employee_id).order_by(FaceEncoding.is_primary.desc())
    )
    face_encoding = face_res.scalars().first()
    face_img = f"/api/v1/biometric-images/{employee_id}/{face_encoding.image_path.replace(chr(92), '/').split('/')[-1]}" if face_encoding and face_encoding.image_path else "/static/default_avatar.png"

    # Get today's logs
    today_start = datetime.combine(date.today(), time.min)
    today_logs_res = await db.execute(
        select(AttendanceLog).where(
            and_(AttendanceLog.employee_id == employee_id, AttendanceLog.timestamp >= today_start)
        ).order_by(AttendanceLog.timestamp)
    )
    today_logs = today_logs_res.scalars().all()

    check_in = None
    check_out = None
    latest_snapshot = None
    is_late = False
    late_text = "On Time"
    policy = await _active_policy(db)
    shift_start = time.fromisoformat(policy.start_time if policy else "09:00")
    late_after = shift_start.hour * 60 + shift_start.minute + int(policy.grace_minutes if policy else 15)

    for l in today_logs:
        if l.event_type == EventType.CHECK_IN and not check_in:
            check_in = l.timestamp.strftime("%I:%M:%S %p")
            if l.timestamp.hour * 60 + l.timestamp.minute > late_after:
                is_late = True
                late_mins = (l.timestamp.hour * 60 + l.timestamp.minute) - late_after
                late_text = f"Late by {late_mins}m"
        elif l.event_type == EventType.CHECK_OUT:
            check_out = l.timestamp.strftime("%I:%M:%S %p")
        if l.face_image_path:
            latest_snapshot = f"/api/v1/audit-images/{l.id}"

    # Get recent 7 logs for audit history
    recent_logs_res = await db.execute(
        select(AttendanceLog).where(AttendanceLog.employee_id == employee_id).order_by(AttendanceLog.timestamp.desc()).limit(7)
    )
    recent_logs = recent_logs_res.scalars().all()

    audit_trail = [
        {
            "id": r.id,
            "event_type": r.event_type.value,
            "timestamp": r.timestamp.strftime("%d %b %Y, %I:%M %p"),
            "confidence": f"{round(r.confidence * 100, 1)}%",
            "snapshot_url": f"/api/v1/audit-images/{r.id}" if r.face_image_path else None,
        }
        for r in recent_logs
    ]

    return {
        "id": employee.id,
        "full_name": employee.full_name,
        "employee_code": employee.employee_code,
        "department": employee.department.name if employee.department else "General",
        "designation": employee.designation or "Staff",
        "phone": employee.phone or "-",
        "email": employee.email or "-",
        "profile_photo": face_img,
        "latest_snapshot": latest_snapshot or face_img,
        "today": {
            "status": "PRESENT" if check_in else "ABSENT",
            "check_in": check_in or "--:--",
            "check_out": check_out or "--:--",
            "is_late": is_late,
            "late_text": late_text,
        },
        "audit_trail": audit_trail,
    }


@router.get("/monthly_summary")
async def get_monthly_attendance_summary(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Get monthly attendance & payroll metrics grouped by employee."""
    return await attendance_service.get_monthly_payroll_summary(db, year, month)


@router.get("/history/{employee_id}")
async def get_employee_history(
    employee_id: int,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Get attendance history for a specific employee."""
    result = await db.execute(select(Employee).where(Employee.id == employee_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Employee not found")
    
    logs = await attendance_service.get_employee_history(
        db, employee_id, start_date, end_date
    )
    
    return {
        "employee_id": employee_id,
        "records": [
            {
                "id": log.id,
                "event_type": log.event_type.value,
                "timestamp": log.timestamp.isoformat(),
                "confidence": log.confidence,
            }
            for log in logs
        ],
    }


@router.post("/manual")
async def manual_attendance(
    request: ManualAttendanceRequest,
    db: AsyncSession = Depends(get_db),
):
    """Manually record attendance (admin override)."""
    result = await db.execute(select(Employee).where(Employee.id == request.employee_id))
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    event_type = EventType(request.event_type)
    
    log = AttendanceLog(
        employee_id=request.employee_id,
        event_type=event_type,
        confidence=1.0,
        timestamp=request.timestamp or datetime.utcnow(),
        metadata_json={"source": "manual_entry"},
    )
    db.add(log)
    await db.flush()
    
    logger.info(f"Manual attendance: Employee {request.employee_id} | {event_type.value}")
    return {"message": "Attendance recorded manually", "id": log.id}


@router.get("/export_csv")
async def export_attendance_csv(db: AsyncSession = Depends(get_db)):
    """Export today's attendance records as a downloadable CSV file."""
    import io
    import csv
    from fastapi.responses import Response
    
    summary = await attendance_service.get_today_summary(db)
    records = summary.get("records", [])
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Employee ID", "Employee Code", "Full Name", "Status", "Check In", "Check Out", "Work Hours"])
    
    for r in records:
        writer.writerow([
            r.get("employee_id"),
            r.get("employee_code"),
            r.get("employee_name"),
            r.get("status"),
            r.get("check_in") or "-",
            r.get("check_out") or "-",
            r.get("work_hours") or "-",
        ])
    
    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=attendance_{date.today().isoformat()}.csv"}
    )

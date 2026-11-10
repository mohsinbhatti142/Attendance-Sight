"""
Attendance Service - Core business logic for attendance tracking.

Handles:
- Recording check-in/check-out events
- Preventing duplicate entries (cooldown period)
- Daily attendance summaries
- Working hours calculation
"""
from datetime import datetime, date, timedelta, time
from typing import Optional

from sqlalchemy import select, func, and_, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import AttendanceLog, Employee, EventType, ShiftPolicy
from src.utils.logger import logger
from src.core.config import get_settings

settings = get_settings()

# Cooldown period: minimum time between consecutive logs for same employee (minutes)
ATTENDANCE_COOLDOWN_MINUTES = 5

# Office timing defaults
OFFICE_START_TIME = time(9, 0)   # 9:00 AM
LATE_THRESHOLD = time(9, 15)      # 9:15 AM — after this = "LATE"
HALF_DAY_TIME = time(13, 0)       # 1:00 PM
OFFICE_END_TIME = time(18, 0)     # 6:00 PM


class AttendanceService:
    """Handles attendance recording and reporting."""
    
    async def record_attendance(
        self,
        db: AsyncSession,
        employee_id: int,
        event_type: EventType,
        confidence: float,
        camera_id: Optional[int] = None,
        face_image_path: Optional[str] = None,
    ) -> Optional[AttendanceLog]:
        """
        Record an attendance event (check-in or check-out).
        
        Implements cooldown to prevent rapid duplicate entries.
        For example, if an employee walks past the camera multiple times
        in 5 minutes, only the first detection is logged.
        """
        # Check cooldown — prevent duplicate entries
        cooldown_time = datetime.utcnow() - timedelta(minutes=ATTENDANCE_COOLDOWN_MINUTES)
        
        stmt = select(AttendanceLog).where(
            and_(
                AttendanceLog.employee_id == employee_id,
                AttendanceLog.timestamp >= cooldown_time,
            )
        ).order_by(AttendanceLog.timestamp.desc()).limit(1)
        
        result = await db.execute(stmt)
        recent_log = result.scalar_one_or_none()
        
        if recent_log:
            logger.debug(
                f"Cooldown active for employee {employee_id}. "
                f"Last log: {recent_log.timestamp} ({recent_log.event_type})"
            )
            return None  # Within cooldown period
        
        # Create attendance log
        log = AttendanceLog(
            employee_id=employee_id,
            camera_id=camera_id,
            event_type=event_type,
            confidence=confidence,
            face_image_path=face_image_path,
        )
        
        db.add(log)
        await db.flush()
        
        logger.info(
            f"Attendance recorded: Employee {employee_id} | "
            f"Type: {event_type.value} | Confidence: {confidence:.4f}"
        )
        
        return log
    
    async def auto_determine_event_type(
        self,
        db: AsyncSession,
        employee_id: int,
    ) -> EventType:
        """
        Automatically determine if this is a CHECK_IN or CHECK_OUT.
        
        Logic:
        - If no log today → CHECK_IN
        - If last log was CHECK_IN → CHECK_OUT
        - If last log was CHECK_OUT → CHECK_IN
        """
        today_start = datetime.combine(date.today(), time.min)
        
        stmt = select(AttendanceLog).where(
            and_(
                AttendanceLog.employee_id == employee_id,
                AttendanceLog.timestamp >= today_start,
            )
        ).order_by(AttendanceLog.timestamp.desc()).limit(1)
        
        result = await db.execute(stmt)
        last_log = result.scalar_one_or_none()
        
        if last_log is None:
            return EventType.CHECK_IN
        elif last_log.event_type == EventType.CHECK_IN:
            return EventType.CHECK_OUT
        else:
            return EventType.CHECK_IN
    
    async def get_today_summary(
        self,
        db: AsyncSession,
    ) -> dict:
        """Get today's attendance summary for all employees."""
        today_start = datetime.combine(date.today(), time.min)
        
        # Get all active employees
        emp_stmt = select(Employee).where(Employee.is_active == True)
        emp_result = await db.execute(emp_stmt)
        employees = emp_result.scalars().all()
        
        # Get today's logs
        log_stmt = select(AttendanceLog).where(
            AttendanceLog.timestamp >= today_start
        ).order_by(AttendanceLog.employee_id, AttendanceLog.timestamp)
        
        log_result = await db.execute(log_stmt)
        logs = log_result.scalars().all()
        
        # Group logs by employee
        employee_logs: dict[int, list[AttendanceLog]] = {}
        for log in logs:
            if log.employee_id not in employee_logs:
                employee_logs[log.employee_id] = []
            employee_logs[log.employee_id].append(log)
        
        # Build summary
        records = []
        present_count = 0
        absent_count = 0
        late_count = 0
        
        for emp in employees:
            emp_logs = employee_logs.get(emp.id, [])
            
            if not emp_logs:
                records.append({
                    "employee_id": emp.id,
                    "employee_name": emp.full_name,
                    "employee_code": emp.employee_code,
                    "check_in": None,
                    "check_out": None,
                    "status": "ABSENT",
                    "work_hours": None,
                })
                absent_count += 1
                continue
            
            # Find first check_in and last check_out
            check_in = None
            check_out = None
            for log in emp_logs:
                if log.event_type == EventType.CHECK_IN and check_in is None:
                    check_in = log.timestamp
                if log.event_type == EventType.CHECK_OUT:
                    check_out = log.timestamp
            
            # Determine status
            status = "PRESENT"
            if check_in:
                check_in_time = check_in.time()
                if check_in_time > LATE_THRESHOLD:
                    status = "LATE"
                    late_count += 1
                elif check_in_time > HALF_DAY_TIME:
                    status = "HALF_DAY"
                else:
                    present_count += 1
            
            # Calculate work hours
            work_hours = None
            if check_in and check_out:
                delta = check_out - check_in
                work_hours = round(delta.total_seconds() / 3600, 2)
            
            records.append({
                "employee_id": emp.id,
                "employee_name": emp.full_name,
                "employee_code": emp.employee_code,
                "check_in": check_in,
                "check_out": check_out,
                "status": status,
                "work_hours": work_hours,
            })
        
        return {
            "date": date.today().isoformat(),
            "total_employees": len(employees),
            "present": present_count,
            "absent": absent_count,
            "late": late_count,
            "records": records,
        }
    
    async def get_employee_history(
        self,
        db: AsyncSession,
        employee_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[AttendanceLog]:
        """Get attendance history for a specific employee."""
        stmt = select(AttendanceLog).where(
            AttendanceLog.employee_id == employee_id
        )
        
        if start_date:
            stmt = stmt.where(
                AttendanceLog.timestamp >= datetime.combine(start_date, time.min)
            )
        if end_date:
            stmt = stmt.where(
                AttendanceLog.timestamp <= datetime.combine(end_date, time.max)
            )
        
        stmt = stmt.order_by(AttendanceLog.timestamp.desc())
        
        result = await db.execute(stmt)
        return result.scalars().all()

    async def get_monthly_payroll_summary(self, db: AsyncSession, year: int = None, month: int = None) -> list[dict]:
        """Compute monthly payroll & attendance breakdown per employee."""
        today = date.today()
        year = year or today.year
        month = month or today.month
        policy = await db.scalar(select(ShiftPolicy).where(ShiftPolicy.is_active.is_(True)).order_by(ShiftPolicy.id).limit(1))
        work_days = set(policy.work_days if policy else [0, 1, 2, 3, 4, 5])
        shift_start = time.fromisoformat(policy.start_time if policy else "09:00")
        late_after = shift_start.hour * 60 + shift_start.minute + int(policy.grace_minutes if policy else 15)
        overtime_after = float(policy.overtime_after_hours if policy else 9.0)
        half_day_hours = float(policy.half_day_hours if policy else 4.0)

        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, month + 1, 1) - timedelta(days=1)

        emp_stmt = select(Employee).where(Employee.is_active == True).order_by(Employee.full_name)
        employees = (await db.execute(emp_stmt)).scalars().all()

        log_stmt = select(AttendanceLog).where(
            and_(
                AttendanceLog.timestamp >= datetime.combine(start_date, time.min),
                AttendanceLog.timestamp <= datetime.combine(end_date, time.max),
            )
        ).order_by(AttendanceLog.timestamp)
        logs = (await db.execute(log_stmt)).scalars().all()

        emp_daily: dict[int, dict[date, list[AttendanceLog]]] = {}
        for l in logs:
            ldate = l.timestamp.date()
            if l.employee_id not in emp_daily:
                emp_daily[l.employee_id] = {}
            if ldate not in emp_daily[l.employee_id]:
                emp_daily[l.employee_id][ldate] = []
            emp_daily[l.employee_id][ldate].append(l)

        summary = []
        for emp in employees:
            # Modular: Calculate working days specifically from this employee's joining/creation date
            emp_join = emp.joining_date or (emp.created_at.date() if emp.created_at else start_date)
            emp_start = max(start_date, emp_join)
            emp_end = min(end_date, today)

            emp_working_days = 0
            if emp_start <= emp_end:
                cur = emp_start
                while cur <= emp_end:
                    if cur.weekday() in work_days:
                        emp_working_days += 1
                    cur += timedelta(days=1)

            days_data = emp_daily.get(emp.id, {})
            present_days = len(days_data)

            # Ensure working days is at least present days and non-zero
            emp_working_days = max(emp_working_days, present_days, 1)

            late_days = 0
            half_day_days = 0
            total_hours = 0.0
            overtime_hours = 0.0

            for d, dlogs in days_data.items():
                in_logs = [x for x in dlogs if x.event_type == EventType.CHECK_IN]
                out_logs = [x for x in dlogs if x.event_type == EventType.CHECK_OUT]
                
                if in_logs:
                    first_in = min(in_logs, key=lambda x: x.timestamp).timestamp
                    if first_in.hour * 60 + first_in.minute > late_after:
                        late_days += 1
                    
                    if out_logs:
                        last_out = max(out_logs, key=lambda x: x.timestamp).timestamp
                        hrs = max(0.0, (last_out - first_in).total_seconds() / 3600.0)
                        total_hours += hrs
                        if hrs < half_day_hours:
                            half_day_days += 1
                        overtime_hours += max(0.0, hrs - overtime_after)
                    else:
                        total_hours += 8.0
                elif dlogs:
                    total_hours += 8.0

            absent_days = max(0, emp_working_days - present_days)
            ot_hours = overtime_hours
            att_rate = round((present_days / emp_working_days) * 100.0, 1) if emp_working_days > 0 else 100.0

            summary.append({
                "employee_id": emp.id,
                "employee_name": emp.full_name,
                "employee_code": emp.employee_code,
                "department": emp.department.name if emp.department else "General",
                "designation": emp.designation or "Staff",
                "working_days": emp_working_days,
                "present_days": present_days,
                "late_days": late_days,
                "half_day_days": half_day_days,
                "absent_days": absent_days,
                "total_hours": round(total_hours, 1),
                "overtime_hours": round(ot_hours, 1),
                "overtime_credit_hours": round(ot_hours * float(policy.overtime_multiplier if policy else 1.5), 1),
                "attendance_rate": att_rate,
            })

        return summary


# Service instance
attendance_service = AttendanceService()

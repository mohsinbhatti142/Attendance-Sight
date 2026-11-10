"""
Database seeder for Attendance-Sight local development.

Populates realistic commercial dummy data:
- Departments (Engineering, HR, Finance, Operations, Marketing)
- Employees across departments with codes, designations, emails
- 30-day realistic attendance history (Presents, Lates, Overtime, Check-in/out timestamps)
"""
import asyncio
import random
from datetime import datetime, date, timedelta, time

from src.db.database import AsyncSessionLocal, init_db
from src.db.models import Department, Employee, AttendanceLog, EventType
from src.utils.logger import logger, setup_logger


DEPARTMENTS_DATA = [
    {"name": "Engineering & Technology", "code": "ENG", "description": "Software, AI & Hardware Infrastructure"},
    {"name": "Human Resources", "code": "HR", "description": "Talent, People Operations & Compliance"},
    {"name": "Operations & Logistics", "code": "OPS", "description": "Supply Chain, Fleet & Facility Management"},
    {"name": "Finance & Accounts", "code": "FIN", "description": "Financial Control, Payroll & Auditing"},
    {"name": "Sales & Business Dev", "code": "SBD", "description": "Enterprise Accounts & Market Growth"},
]

EMPLOYEES_DATA = [
    {"code": "EMP-1042", "name": "Ali Khan", "dept": "ENG", "desig": "Principal AI Architect", "email": "ali.khan@enterprise.com", "phone": "+92 300 1234567"},
    {"code": "EMP-1043", "name": "Fatima Zahra", "dept": "HR", "desig": "Head of Human Resources", "email": "fatima.z@enterprise.com", "phone": "+92 301 2345678"},
    {"code": "EMP-1044", "name": "Usman Tariq", "dept": "ENG", "desig": "Senior Full-Stack Engineer", "email": "usman.t@enterprise.com", "phone": "+92 302 3456789"},
    {"code": "EMP-1045", "name": "Ayesha Malik", "dept": "FIN", "desig": "Financial Controller", "email": "ayesha.m@enterprise.com", "phone": "+92 303 4567890"},
    {"code": "EMP-1046", "name": "Bilal Ahmed", "dept": "OPS", "desig": "Operations Director", "email": "bilal.a@enterprise.com", "phone": "+92 304 5678901"},
    {"code": "EMP-1047", "name": "Zainab Bibi", "dept": "SBD", "desig": "Enterprise Sales Lead", "email": "zainab.b@enterprise.com", "phone": "+92 305 6789012"},
    {"code": "EMP-1048", "name": "Hamza Siddiqui", "dept": "ENG", "desig": "Cloud & DevOps Specialist", "email": "hamza.s@enterprise.com", "phone": "+92 306 7890123"},
    {"code": "EMP-1049", "name": "Sana Mir", "dept": "HR", "desig": "Talent Acquisition Manager", "email": "sana.m@enterprise.com", "phone": "+92 307 8901234"},
    {"code": "EMP-1050", "name": "Omer Farooq", "dept": "OPS", "desig": "Fleet & Facilities Lead", "email": "omer.f@enterprise.com", "phone": "+92 308 9012345"},
    {"code": "EMP-1051", "name": "Mariam Javed", "dept": "ENG", "desig": "Lead Product Designer", "email": "mariam.j@enterprise.com", "phone": "+92 309 0123456"},
    {"code": "EMP-1052", "name": "Danish Qureshi", "dept": "FIN", "desig": "Senior Payroll Accountant", "email": "danish.q@enterprise.com", "phone": "+92 310 1234567"},
    {"code": "EMP-1053", "name": "Hira Nadeem", "dept": "SBD", "desig": "Client Success Specialist", "email": "hira.n@enterprise.com", "phone": "+92 311 2345678"},
]


async def seed_database():
    setup_logger()
    logger.info("Initializing database schema...")
    await init_db()

    async with AsyncSessionLocal() as session:
        from sqlalchemy import select, delete

        # Check existing departments
        dept_result = await session.execute(select(Department))
        dept_map = {d.code: d for d in dept_result.scalars().all()}

        if not dept_map:
            logger.info("Creating departments...")
            for d_data in DEPARTMENTS_DATA:
                dept = Department(
                    name=d_data["name"],
                    code=d_data["code"],
                    description=d_data["description"],
                )
                session.add(dept)
                dept_map[d_data["code"]] = dept
            await session.flush()

        # Check existing employees
        emp_result = await session.execute(select(Employee))
        existing_employees = {e.employee_code: e for e in emp_result.scalars().all()}
        
        created_employees = []
        for e_data in EMPLOYEES_DATA:
            if e_data["code"] in existing_employees:
                created_employees.append(existing_employees[e_data["code"]])
                continue

            dept = dept_map.get(e_data["dept"])
            emp = Employee(
                employee_code=e_data["code"],
                full_name=e_data["name"],
                email=e_data["email"],
                phone=e_data["phone"],
                designation=e_data["desig"],
                department_id=dept.id if dept else None,
                joining_date=date.today() - timedelta(days=random.randint(100, 800)),
                is_active=True,
            )
            session.add(emp)
            created_employees.append(emp)

        await session.flush()
        logger.info(f"Loaded {len(created_employees)} employees.")

        # Check existing attendance logs
        log_count_res = await session.execute(select(AttendanceLog))
        existing_logs = log_count_res.scalars().all()

        if len(existing_logs) < 50:
            logger.info("Seeding past 30 days of attendance history...")
            today = date.today()

            for day_offset in range(30, -1, -1):
                target_date = today - timedelta(days=day_offset)
                
                # Skip Sundays
                if target_date.weekday() == 6:
                    continue

                for emp in created_employees:
                    # 92% attendance probability
                    if random.random() > 0.92:
                        continue  # Absent today

                    # In-time simulation (75% on time, 25% slightly late)
                    if random.random() < 0.75:
                        in_hour = 8
                        in_minute = random.randint(45, 59)
                    else:
                        in_hour = 9
                        in_minute = random.randint(5, 40)

                    check_in_dt = datetime.combine(target_date, time(in_hour, in_minute))
                    conf_score = round(random.uniform(0.85, 0.97), 4)

                    # Create Check-In Log
                    in_log = AttendanceLog(
                        employee_id=emp.id,
                        event_type=EventType.CHECK_IN,
                        timestamp=check_in_dt,
                        confidence=conf_score,
                        metadata_json={"source": "biometric_kiosk", "day_offset": day_offset},
                    )
                    session.add(in_log)

                    # If not today, or if afternoon, add Check-Out
                    if day_offset > 0 or datetime.now().hour >= 18:
                        out_hour = random.choice([17, 18, 18, 19])
                        out_minute = random.randint(0, 50)
                        check_out_dt = datetime.combine(target_date, time(out_hour, out_minute))

                        out_log = AttendanceLog(
                            employee_id=emp.id,
                            event_type=EventType.CHECK_OUT,
                            timestamp=check_out_dt,
                            confidence=round(random.uniform(0.86, 0.98), 4),
                            metadata_json={"source": "biometric_kiosk"},
                        )
                        session.add(out_log)

            await session.commit()
            logger.info("✅ Past 30 days attendance history seeded successfully!")
        else:
            logger.info(f"Database already contains {len(existing_logs)} attendance logs.")


if __name__ == "__main__":
    asyncio.run(seed_database())

from typing import Any, Dict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.session import AsyncSessionLocal
from app.models.job import Job, JobStatus
from app.models.user import Role, User
from app.services.email_service import EmailService

logger = structlog.get_logger()


async def send_weekly_digest_task(ctx: Dict[str, Any]) -> str:
    """Weekly background cron job: Send digest of active drives to students."""
    logger.info("send_weekly_digest_started")

    async with AsyncSessionLocal() as db:
        # Count open drives
        active_jobs = await db.scalar(
            select(func.count(Job.id)).where(
                Job.status.in_([JobStatus.OPEN, JobStatus.CLOSING_SOON])
            )
        ) or 0

        # Query all active students
        result = await db.execute(
            select(User).where(User.role == Role.STUDENT, User.is_active.is_(True))
        )
        students = list(result.scalars().all())

        sent_count = 0
        for student in students:
            success = await EmailService.send_weekly_digest(
                to_email=student.email,
                student_name=student.name,
                active_jobs_count=active_jobs,
                batch_rank=12,
            )
            if success:
                sent_count += 1

        logger.info("send_weekly_digest_completed", sent=sent_count, total=len(students))
        return f"sent_{sent_count}_digests"

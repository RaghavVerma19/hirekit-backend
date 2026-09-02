from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.session import AsyncSessionLocal
from app.models.job import Job, JobStatus

logger = structlog.get_logger()


async def check_job_deadlines_task(ctx: Dict[str, Any]) -> str:
    """Daily background task to update expiring and expired job statuses."""
    now = datetime.now(timezone.utc)
    closing_soon_threshold = now + timedelta(hours=48)

    async with AsyncSessionLocal() as db:
        # 1. Close expired jobs
        closed_res = await db.execute(
            update(Job)
            .where(Job.deadline < now, Job.status != JobStatus.CLOSED)
            .values(status=JobStatus.CLOSED)
        )

        # 2. Mark closing soon jobs
        soon_res = await db.execute(
            update(Job)
            .where(
                Job.deadline >= now,
                Job.deadline <= closing_soon_threshold,
                Job.status == JobStatus.OPEN,
            )
            .values(status=JobStatus.CLOSING_SOON)
        )
        await db.commit()

        logger.info(
            "check_job_deadlines_completed",
            closed_count=closed_res.rowcount,
            closing_soon_count=soon_res.rowcount,
        )
        return f"closed_{closed_res.rowcount}_expiring_{soon_res.rowcount}"

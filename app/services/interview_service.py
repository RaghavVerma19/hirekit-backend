from datetime import datetime, timezone
from typing import List, Optional
import uuid
from fastapi import status
import redis.asyncio as aioredis
from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.errors import AppException
from app.models.application import Application, ApplicationEvent, ApplicationStatus
from app.models.interview import Interview, InterviewStatus
from app.models.notification import NotificationType
from app.schemas.interview import InterviewCreate
from app.services.notification_service import NotificationService

logger = structlog.get_logger()


class InterviewService:
    @staticmethod
    async def schedule_interview(
        db: AsyncSession, redis: aioredis.Redis, create_in: InterviewCreate
    ) -> Interview:
        """Schedule interview, link to application timeline, and notify candidate."""
        interview = Interview(
            user_id=create_in.user_id,
            application_id=create_in.application_id,
            company_name=create_in.company_name,
            role_title=create_in.role_title,
            round_name=create_in.round_name,
            scheduled_at=create_in.scheduled_at,
            meeting_url=create_in.meeting_url,
            status=InterviewStatus.SCHEDULED,
        )
        db.add(interview)
        await db.flush()

        # Update application timeline if linked
        if create_in.application_id:
            application = await db.get(Application, create_in.application_id)
            if application:
                application.status = ApplicationStatus.INTERVIEW_SCHEDULED
                event = ApplicationEvent(
                    application_id=application.id,
                    status=ApplicationStatus.INTERVIEW_SCHEDULED,
                    actor="TPO",
                    note=f"{create_in.round_name} scheduled for {create_in.scheduled_at.strftime('%b %d, %Y %I:%M %p')}.",
                )
                db.add(event)

        await db.commit()
        await db.refresh(interview)

        # Notify student via Pub/Sub
        await NotificationService.create_and_publish(
            db=db,
            redis=redis,
            user_id=create_in.user_id,
            title=f"Interview Scheduled: {create_in.company_name}",
            body=f"Your {create_in.round_name} for {create_in.role_title} has been scheduled for {create_in.scheduled_at.strftime('%b %d, %I:%M %p')}.",
            notif_type=NotificationType.INTERVIEW,
            link=f"/interviews",
        )

        return interview

    @staticmethod
    async def list_upcoming(
        db: AsyncSession, user_id: uuid.UUID
    ) -> List[Interview]:
        """Fetch student's upcoming interviews."""
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(Interview)
            .where(
                Interview.user_id == user_id,
                Interview.scheduled_at >= now,
                Interview.status != InterviewStatus.CANCELLED,
            )
            .order_by(asc(Interview.scheduled_at))
        )
        return list(result.scalars().all())

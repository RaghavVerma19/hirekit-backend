from datetime import datetime, timezone
from typing import List, Optional
import uuid
from fastapi import status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import structlog

from app.core.errors import AppException
from app.models.application import Application, ApplicationEvent, ApplicationStatus
from app.models.education import Education
from app.models.job import Job, JobStatus
from app.models.resume import Resume
from app.models.user import User

logger = structlog.get_logger()


class ApplicationService:
    @staticmethod
    async def list_applications(
        db: AsyncSession, user_id: uuid.UUID
    ) -> List[Application]:
        """List all job applications for a student with job details and timeline."""
        result = await db.execute(
            select(Application)
            .where(Application.user_id == user_id)
            .options(
                selectinload(Application.job),
                selectinload(Application.events),
            )
            .order_by(desc(Application.applied_at))
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_application(
        db: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID
    ) -> Application:
        """Fetch single application with timeline events and ownership check."""
        result = await db.execute(
            select(Application)
            .where(Application.id == application_id, Application.user_id == user_id)
            .options(
                selectinload(Application.job),
                selectinload(Application.events),
            )
        )
        app_record = result.scalar_one_or_none()
        if not app_record:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="APPLICATION_NOT_FOUND",
                message="Application record not found.",
            )
        return app_record

    @staticmethod
    async def apply(
        db: AsyncSession,
        user: User,
        job_id: uuid.UUID,
        resume_id: Optional[uuid.UUID] = None,
    ) -> Application:
        """1-Click apply with eligibility pre-checks, resume resolution, and idempotency."""
        # 1. Fetch Job
        job = await db.get(Job, job_id)
        if not job:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="JOB_NOT_FOUND",
                message="Job posting not found.",
            )

        # 2. Check Job Status & Deadline
        deadline = job.deadline.replace(tzinfo=timezone.utc) if job.deadline.tzinfo is None else job.deadline
        if job.status == JobStatus.CLOSED or deadline < datetime.now(timezone.utc):
            raise AppException(
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="JOB_DEADLINE_EXPIRED",
                message="This drive is closed for new applications.",
            )

        # 3. Idempotent check: Has the student already applied?
        existing_res = await db.execute(
            select(Application)
            .where(Application.user_id == user.id, Application.job_id == job.id)
            .options(
                selectinload(Application.job),
                selectinload(Application.events),
            )
        )
        existing_app = existing_res.scalar_one_or_none()
        if existing_app:
            logger.info(
                "application_idempotent_hit",
                user_id=str(user.id),
                job_id=str(job.id),
            )
            return existing_app

        # 4. Check Minimum CGPA Eligibility
        if job.min_cgpa > 0:
            edu_res = await db.execute(
                select(Education).where(Education.user_id == user.id)
            )
            educations = list(edu_res.scalars().all())
            user_cgpa = max([e.cgpa for e in educations if e.cgpa] or [0.0])

            if user_cgpa > 0 and user_cgpa < job.min_cgpa:
                raise AppException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    error_code="INELIGIBLE_CGPA",
                    message=f"Your CGPA ({user_cgpa:.1f}) is below the required minimum of {job.min_cgpa}.",
                )

        # 5. Resolve Resume
        resolved_resume_id = resume_id
        if not resolved_resume_id:
            # Fallback to user's primary resume
            prim_res = await db.execute(
                select(Resume.id).where(
                    Resume.user_id == user.id,
                    Resume.is_primary.is_(True),
                    Resume.is_deleted.is_(False),
                )
            )
            resolved_resume_id = prim_res.scalar_one_or_none()

            # If no primary resume, pick any active resume
            if not resolved_resume_id:
                any_res = await db.execute(
                    select(Resume.id).where(
                        Resume.user_id == user.id, Resume.is_deleted.is_(False)
                    )
                )
                resolved_resume_id = any_res.scalar_one_or_none()

        if not resolved_resume_id:
            raise AppException(
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="RESUME_REQUIRED",
                message="Please create or upload a resume before applying for jobs.",
            )

        # 6. Create Application and initial Timeline Event
        new_application = Application(
            job_id=job.id,
            user_id=user.id,
            resume_id=resolved_resume_id,
            status=ApplicationStatus.APPLIED,
        )
        db.add(new_application)
        await db.flush()

        event = ApplicationEvent(
            application_id=new_application.id,
            status=ApplicationStatus.APPLIED,
            actor="STUDENT",
            note="Application submitted with primary resume.",
        )
        db.add(event)
        await db.commit()

        # Reload full application
        return await ApplicationService.get_application(db, user.id, new_application.id)

    @staticmethod
    async def withdraw(
        db: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID
    ) -> Application:
        """Withdraw an active application."""
        application = await ApplicationService.get_application(db, user_id, application_id)
        if application.status in [ApplicationStatus.OFFERED, ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN]:
            raise AppException(
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="CANNOT_WITHDRAW",
                message=f"Cannot withdraw an application in status '{application.status}'.",
            )

        application.status = ApplicationStatus.WITHDRAWN
        event = ApplicationEvent(
            application_id=application.id,
            status=ApplicationStatus.WITHDRAWN,
            actor="STUDENT",
            note="Application withdrawn by student.",
        )
        db.add(event)
        await db.commit()
        await db.refresh(application)
        return application

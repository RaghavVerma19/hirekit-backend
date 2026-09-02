from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
from fastapi import status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import structlog

from app.core.errors import AppException
from app.models.experience import Experience
from app.models.resume import Resume
from app.models.user import User
from app.schemas.resume import ResumeCreate, ResumeDetailOut, ResumeOut, ResumeUpdate
from app.services.ats_service import ATSService

logger = structlog.get_logger()

MAX_RESUMES_PER_USER = 10


class ResumeService:
    @staticmethod
    async def list_resumes(db: AsyncSession, user_id: uuid.UUID) -> List[Resume]:
        """List active resumes for a user."""
        result = await db.execute(
            select(Resume)
            .where(Resume.user_id == user_id, Resume.is_deleted.is_(False))
            .order_by(Resume.is_primary.desc(), Resume.updated_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_resume(
        db: AsyncSession, user_id: Optional[uuid.UUID], resume_id: uuid.UUID
    ) -> Resume:
        """Fetch resume with ownership verification (public link passes user_id=None)."""
        resume = await db.get(Resume, resume_id)
        if not resume or resume.is_deleted:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="RESUME_NOT_FOUND",
                message="Resume not found.",
            )

        if user_id is not None and resume.user_id != user_id:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="RESUME_NOT_FOUND",
                message="Resume not found.",
            )

        return resume

    @staticmethod
    async def create_resume(
        db: AsyncSession, user_id: uuid.UUID, create_in: ResumeCreate
    ) -> Resume:
        """Create a resume, auto-populating sections from profile if requested."""
        count = await db.scalar(
            select(func.count(Resume.id)).where(
                Resume.user_id == user_id, Resume.is_deleted.is_(False)
            )
        )
        if count >= MAX_RESUMES_PER_USER:
            raise AppException(
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="MAX_RESUMES_EXCEEDED",
                message=f"You can create a maximum of {MAX_RESUMES_PER_USER} resumes.",
            )

        # Build content JSON
        content: Dict[str, Any] = {
            "title": create_in.title,
            "personal": {},
            "summary": "",
            "education": [],
            "experience": [],
            "projects": [],
            "skills": [],
        }

        if create_in.auto_populate:
            # Eager load user profile data
            result = await db.execute(
                select(User)
                .where(User.id == user_id)
                .options(
                    selectinload(User.educations),
                    selectinload(User.experiences).selectinload(Experience.responsibilities) if hasattr(User, "experiences") else selectinload(User.educations),
                    selectinload(User.skills),
                    selectinload(User.projects),
                )
            )
            user = result.scalar_one_or_none()
            if user:
                content["personal"] = {
                    "name": user.name,
                    "email": user.email,
                    "phone": user.phone or "",
                    "location": user.location or "",
                    "headline": user.headline or "",
                }
                content["summary"] = user.summary or ""
                content["education"] = [
                    {
                        "degree": e.degree,
                        "institution": e.institution,
                        "start_year": e.start_year,
                        "end_year": e.end_year,
                        "cgpa": e.cgpa,
                    }
                    for e in getattr(user, "educations", [])
                ]
                content["skills"] = [
                    s.name for s in getattr(user, "skills", [])
                ]
                content["projects"] = [
                    {
                        "title": p.title,
                        "description": p.description,
                        "skills": p.skills_used,
                        "live_url": p.live_url,
                        "github_url": p.github_url,
                    }
                    for p in getattr(user, "projects", [])
                ]

        content_hash = ATSService.compute_content_hash(content)
        is_first = count == 0

        new_resume = Resume(
            user_id=user_id,
            title=create_in.title,
            template_id=create_in.template_id,
            content_json=content,
            content_hash=content_hash,
            is_primary=is_first,
            leaderboard_eligible=True,
            is_deleted=False,
        )
        db.add(new_resume)
        await db.commit()
        await db.refresh(new_resume)

        logger.info("resume_created", resume_id=str(new_resume.id), user_id=str(user_id))
        return new_resume

    @staticmethod
    async def update_resume(
        db: AsyncSession,
        user_id: uuid.UUID,
        resume_id: uuid.UUID,
        update_in: ResumeUpdate,
    ) -> Resume:
        """Update resume with optimistic concurrency check."""
        resume = await ResumeService.get_resume(db, user_id, resume_id)

        # Optimistic Concurrency Control
        if update_in.last_known_updated_at:
            if resume.updated_at > update_in.last_known_updated_at:
                raise AppException(
                    status_code=status.HTTP_409_CONFLICT,
                    error_code="CONCURRENT_EDIT_CONFLICT",
                    message="Resume was modified in another session. Please reload the latest changes.",
                )

        if update_in.title is not None:
            resume.title = update_in.title

        if update_in.template_id is not None:
            resume.template_id = update_in.template_id

        if update_in.content_json is not None:
            resume.content_json = update_in.content_json
            resume.content_hash = ATSService.compute_content_hash(update_in.content_json)

        await db.commit()
        await db.refresh(resume)
        return resume

    @staticmethod
    async def set_primary(
        db: AsyncSession, user_id: uuid.UUID, resume_id: uuid.UUID
    ) -> Resume:
        """Set a resume as the primary application resume."""
        resume = await ResumeService.get_resume(db, user_id, resume_id)

        # Unset all other primary resumes for this user
        await db.execute(
            update(Resume)
            .where(Resume.user_id == user_id, Resume.id != resume_id)
            .values(is_primary=False)
        )

        resume.is_primary = True
        await db.commit()
        await db.refresh(resume)
        return resume

    @staticmethod
    async def soft_delete(
        db: AsyncSession, user_id: uuid.UUID, resume_id: uuid.UUID
    ) -> None:
        """Soft-delete a resume."""
        resume = await ResumeService.get_resume(db, user_id, resume_id)
        resume.is_deleted = True
        await db.commit()

from datetime import datetime, timezone
from typing import List, Optional, Tuple
import uuid
from fastapi import status
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppException
from app.models.application import Application
from app.models.education import Education
from app.models.job import Job, JobStatus, JobType
from app.models.skill import UserSkill
from app.models.user import User
from app.schemas.job import JobCreate, JobListItem, JobOut


class JobService:
    @staticmethod
    def check_eligibility(
        user: User,
        job: Job,
        educations: List[Education],
        existing_offers: Optional[List[Application]] = None,
    ) -> Tuple[bool, List[str]]:
        """Evaluate student eligibility against job requirements & institutional policy."""
        reasons: List[str] = []

        # 1. Institutional Tier Policy & Offer Lock
        from app.models.job import JobTier
        if existing_offers:
            for off in existing_offers:
                offered_tier = getattr(off.job, "tier", JobTier.REGULAR) if off.job else JobTier.REGULAR
                if offered_tier == JobTier.SUPER_DREAM:
                    reasons.append("Policy Lock: You have secured a Super Dream offer.")
                    break
                elif offered_tier == JobTier.DREAM and job.tier in [JobTier.REGULAR, JobTier.DREAM]:
                    reasons.append("Policy Lock: Dream offer holders can only apply for Super Dream drives.")
                    break
                elif offered_tier == JobTier.REGULAR and job.tier == JobTier.REGULAR:
                    reasons.append("Policy Lock: Regular offer holders can only apply for Dream or Super Dream drives.")
                    break

        # 2. CGPA check
        if job.min_cgpa > 0:
            user_cgpa = 0.0
            if educations:
                # Get highest/latest degree CGPA
                for edu in educations:
                    if edu.cgpa and edu.cgpa > user_cgpa:
                        user_cgpa = edu.cgpa

            if user_cgpa > 0 and user_cgpa < job.min_cgpa:
                reasons.append(
                    f"Minimum required CGPA is {job.min_cgpa} (Your recorded CGPA: {user_cgpa:.1f})"
                )

        # 3. Department check
        if job.eligible_departments and educations:
            user_depts = [edu.department.lower() for edu in educations if edu.department]
            matched = any(
                any(allowed.lower() in user_dept or user_dept in allowed.lower() for allowed in job.eligible_departments)
                for user_dept in user_depts
            )
            if not matched and user_depts:
                reasons.append(
                    f"Eligible departments: {', '.join(job.eligible_departments)}"
                )

        # 4. Backlog check
        if job.max_active_backlogs >= 0 and educations:
            user_backlogs = sum([getattr(e, "active_backlogs", 0) for e in educations])
            if user_backlogs > job.max_active_backlogs:
                reasons.append(
                    f"Drive permits at most {job.max_active_backlogs} active backlogs (You have {user_backlogs})."
                )

        # 5. Deadline check
        deadline = job.deadline.replace(tzinfo=timezone.utc) if job.deadline.tzinfo is None else job.deadline
        if deadline < datetime.now(timezone.utc) or job.status == JobStatus.CLOSED:
            reasons.append("Application deadline for this drive has passed.")

        is_eligible = len(reasons) == 0
        return is_eligible, reasons

    @staticmethod
    def calculate_match_score(skills: List[UserSkill], job_skills: List[str]) -> int:
        """Calculate technical skill fit score (0-100%)."""
        if not job_skills:
            return 85

        user_skill_names = {s.name.lower() for s in skills}
        matches = sum(1 for req in job_skills if req.lower() in user_skill_names)

        ratio = matches / len(job_skills)
        score = int(60 + (ratio * 38))
        return min(98, max(50, score))

    @staticmethod
    async def list_jobs(
        db: AsyncSession,
        user: Optional[User] = None,
        search: Optional[str] = None,
        job_type: Optional[JobType] = None,
        only_open: bool = True,
    ) -> List[JobListItem]:
        """List jobs with personalized student eligibility & match scores."""
        query = select(Job).order_by(desc(Job.posted_at))

        if only_open:
            query = query.where(Job.status.in_([JobStatus.OPEN, JobStatus.CLOSING_SOON]))

        if job_type:
            query = query.where(Job.type == job_type)

        if search:
            q = f"%{search}%"
            query = query.where(
                or_(
                    Job.title.ilike(q),
                    Job.company_name.ilike(q),
                    Job.location.ilike(q),
                )
            )

        result = await db.execute(query)
        jobs = list(result.scalars().all())

        # If user is authenticated, load educations, skills, and applied job IDs
        educations: List[Education] = []
        skills: List[UserSkill] = []
        applied_job_ids = set()

        if user:
            edu_res = await db.execute(
                select(Education).where(Education.user_id == user.id)
            )
            educations = list(edu_res.scalars().all())

            skill_res = await db.execute(
                select(UserSkill).where(UserSkill.user_id == user.id)
            )
            skills = list(skill_res.scalars().all())

            app_res = await db.execute(
                select(Application.job_id).where(Application.user_id == user.id)
            )
            applied_job_ids = set(app_res.scalars().all())

            offers_res = await db.execute(
                select(Application)
                .join(Job, Application.job_id == Job.id)
                .where(
                    Application.user_id == user.id,
                    Application.status == "OFFERED",
                )
                .options(selectinload(Application.job))
            )
            existing_offers = list(offers_res.scalars().all())

        items: List[JobListItem] = []
        for j in jobs:
            if user:
                is_eligible, reasons = JobService.check_eligibility(
                    user, j, educations, existing_offers
                )
                match_score = JobService.calculate_match_score(skills, j.skills)
                has_applied = j.id in applied_job_ids
            else:
                is_eligible, reasons = True, []
                match_score = 80
                has_applied = False

            item = JobListItem(
                id=j.id,
                title=j.title,
                company_name=j.company_name,
                company_logo=j.company_logo,
                location=j.location,
                type=j.type,
                tier=getattr(j, "tier", "REGULAR"),
                ctc=j.ctc,
                min_cgpa=j.min_cgpa,
                max_active_backlogs=getattr(j, "max_active_backlogs", 0),
                min_10th_marks=getattr(j, "min_10th_marks", 0.0),
                min_12th_marks=getattr(j, "min_12th_marks", 0.0),
                eligible_departments=j.eligible_departments,
                eligible_batches=j.eligible_batches,
                skills=j.skills,
                description=j.description,
                requirements=j.requirements,
                rounds=getattr(j, "rounds", []) or [],
                is_drive_active=getattr(j, "is_drive_active", True),
                status=j.status,
                deadline=j.deadline,
                posted_at=j.posted_at,
                is_eligible=is_eligible,
                ineligibility_reasons=reasons,
                match_score=match_score,
                has_applied=has_applied,
            )
            items.append(item)

        return items

    @staticmethod
    async def get_job(
        db: AsyncSession, job_id: uuid.UUID, user: Optional[User] = None
    ) -> JobListItem:
        """Fetch full job details with user-specific eligibility."""
        job = await db.get(Job, job_id)
        if not job:
            raise AppException(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="JOB_NOT_FOUND",
                message="Job posting not found.",
            )

        educations: List[Education] = []
        skills: List[UserSkill] = []
        existing_offers: List[Application] = []
        has_applied = False

        if user:
            edu_res = await db.execute(
                select(Education).where(Education.user_id == user.id)
            )
            educations = list(edu_res.scalars().all())

            skill_res = await db.execute(
                select(UserSkill).where(UserSkill.user_id == user.id)
            )
            skills = list(skill_res.scalars().all())

            app_res = await db.execute(
                select(Application).where(
                    Application.user_id == user.id, Application.job_id == job.id
                )
            )
            has_applied = app_res.scalar_one_or_none() is not None

            offers_res = await db.execute(
                select(Application)
                .join(Job, Application.job_id == Job.id)
                .where(
                    Application.user_id == user.id,
                    Application.status == "OFFERED",
                )
                .options(selectinload(Application.job))
            )
            existing_offers = list(offers_res.scalars().all())

        is_eligible, reasons = (
            JobService.check_eligibility(user, job, educations, existing_offers)
            if user
            else (True, [])
        )
        match_score = (
            JobService.calculate_match_score(skills, job.skills)
            if user
            else 85
        )

        return JobListItem(
            id=job.id,
            title=job.title,
            company_name=job.company_name,
            company_logo=job.company_logo,
            location=job.location,
            type=job.type,
            tier=getattr(job, "tier", "REGULAR"),
            ctc=job.ctc,
            min_cgpa=job.min_cgpa,
            max_active_backlogs=getattr(job, "max_active_backlogs", 0),
            min_10th_marks=getattr(job, "min_10th_marks", 0.0),
            min_12th_marks=getattr(job, "min_12th_marks", 0.0),
            eligible_departments=job.eligible_departments,
            eligible_batches=job.eligible_batches,
            skills=job.skills,
            description=job.description,
            requirements=job.requirements,
            rounds=getattr(job, "rounds", []) or [],
            is_drive_active=getattr(job, "is_drive_active", True),
            status=job.status,
            deadline=job.deadline,
            posted_at=job.posted_at,
            is_eligible=is_eligible,
            ineligibility_reasons=reasons,
            match_score=match_score,
            has_applied=has_applied,
        )

    @staticmethod
    async def create_job(db: AsyncSession, job_in: JobCreate) -> Job:
        """Create a new campus placement drive (TPO/Admin action)."""
        default_rounds = [
            {"order": 1, "name": "Resume Screening", "type": "SCREENING"},
            {"order": 2, "name": "Online Assessment (OA)", "type": "OA"},
            {"order": 3, "name": "Technical Interview", "type": "INTERVIEW"},
            {"order": 4, "name": "HR & Management Round", "type": "HR"},
        ]
        new_job = Job(
            title=job_in.title,
            company_name=job_in.company_name,
            company_logo=job_in.company_logo,
            location=job_in.location,
            type=job_in.type,
            tier=job_in.tier or "REGULAR",
            ctc=job_in.ctc,
            min_cgpa=job_in.min_cgpa,
            max_active_backlogs=job_in.max_active_backlogs,
            min_10th_marks=job_in.min_10th_marks,
            min_12th_marks=job_in.min_12th_marks,
            eligible_departments=job_in.eligible_departments,
            eligible_batches=job_in.eligible_batches,
            skills=job_in.skills,
            description=job_in.description,
            requirements=job_in.requirements,
            rounds=job_in.rounds or default_rounds,
            is_drive_active=True,
            deadline=job_in.deadline,
        )
        db.add(new_job)
        await db.commit()
        await db.refresh(new_job)
        return new_job

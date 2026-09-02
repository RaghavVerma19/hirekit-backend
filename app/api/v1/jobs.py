from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.job import Job, JobStatus, JobType
from app.models.user import User
from app.schemas.application import ApplicationCreate, ApplicationDetailOut
from app.schemas.job import JobCreate, JobListItem, JobOut
from app.services.application_service import ApplicationService
from app.services.job_service import JobService

router = APIRouter(prefix="/jobs", tags=["Jobs & Opportunities"])


@router.post(
    "",
    response_model=JobOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create Campus Job Posting",
)
async def create_job(
    job_in: JobCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobOut:
    """Create a new job posting."""
    job = Job(
        title=job_in.title,
        company_name=job_in.company_name,
        company_logo=job_in.company_logo,
        location=job_in.location,
        type=job_in.type,
        ctc=job_in.ctc,
        min_cgpa=job_in.min_cgpa,
        eligible_departments=job_in.eligible_departments,
        eligible_batches=job_in.eligible_batches,
        skills=job_in.skills,
        description=job_in.description,
        requirements=job_in.requirements,
        deadline=job_in.deadline,
        status=JobStatus.OPEN,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return JobOut.model_validate(job)


@router.get(
    "",
    response_model=List[JobListItem],
    status_code=status.HTTP_200_OK,
    summary="List Campus Jobs & Placements",
)
async def list_jobs(
    search: Optional[str] = Query(None, description="Search by title, company or location"),
    type: Optional[JobType] = Query(None, description="Filter by job type"),
    only_open: bool = Query(True, description="Only show open drives"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[JobListItem]:
    """List opportunities with personalized eligibility checks and skills match scores."""
    return await JobService.list_jobs(
        db=db,
        user=current_user,
        search=search,
        job_type=type,
        only_open=only_open,
    )


@router.get(
    "/{job_id}",
    response_model=JobListItem,
    status_code=status.HTTP_200_OK,
    summary="Get Job Details & Eligibility Breakdown",
)
async def get_job_detail(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobListItem:
    """Fetch complete job description, requirements, and candidate eligibility criteria."""
    return await JobService.get_job(db, job_id, current_user)


@router.post(
    "/{job_id}/apply",
    response_model=ApplicationDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="1-Click Apply with Resume",
)
async def apply_to_job(
    job_id: uuid.UUID,
    apply_in: ApplicationCreate = ApplicationCreate(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplicationDetailOut:
    """Submit 1-click application with automated eligibility verification and timeline event."""
    application = await ApplicationService.apply(
        db=db,
        user=current_user,
        job_id=job_id,
        resume_id=apply_in.resume_id,
    )
    return ApplicationDetailOut.model_validate(application)

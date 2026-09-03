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
    """Create a new campus placement drive."""
    job = await JobService.create_job(db, job_in)
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


@router.delete(
    "/{job_id}",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Delete Job Drive",
)
async def delete_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    job = await db.get(Job, job_id)
    if not job:
        return {"message": "Job not found"}
    await db.delete(job)
    await db.commit()
    return {"message": "Job drive deleted successfully"}


@router.get(
    "/{job_id}/applicants",
    response_model=List[dict],
    status_code=status.HTTP_200_OK,
    summary="List All Drive Applicants with Round & Academic Breakdown",
)
async def list_job_applicants(
    job_id: uuid.UUID,
    round_number: Optional[int] = Query(None, description="Filter by active round"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[dict]:
    """Retrieve full candidate roster for a placement drive (TPO & Recruiter portal)."""
    from app.models.application import Application
    from app.models.education import Education
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    query = (
        select(Application)
        .where(Application.job_id == job_id)
        .options(selectinload(Application.user), selectinload(Application.resume))
        .order_by(Application.applied_at.asc())
    )
    if round_number is not None:
        query = query.where(Application.current_round == round_number)

    res = await db.execute(query)
    apps = list(res.scalars().all())

    user_ids = [a.user_id for a in apps]
    educations_by_user = {}
    if user_ids:
        edu_res = await db.execute(
            select(Education).where(Education.user_id.in_(user_ids))
        )
        for edu in edu_res.scalars().all():
            if edu.user_id not in educations_by_user:
                educations_by_user[edu.user_id] = []
            educations_by_user[edu.user_id].append(edu)

    output = []
    for a in apps:
        edus = educations_by_user.get(a.user_id, [])
        cgpa = max([e.cgpa for e in edus if e.cgpa] or [0.0])
        dept = edus[0].department if edus and edus[0].department else "Engineering"
        backlogs = sum([getattr(e, "active_backlogs", 0) for e in edus])

        output.append({
            "application_id": str(a.id),
            "user_id": str(a.user_id),
            "name": a.user.name if a.user else "Candidate",
            "email": a.user.email if a.user else "",
            "phone": a.user.phone if a.user else "",
            "avatar_url": a.user.avatar_url if a.user else None,
            "cgpa": cgpa,
            "department": dept,
            "active_backlogs": backlogs,
            "status": a.status,
            "current_round": a.current_round,
            "applied_at": a.applied_at.isoformat(),
            "offer_ctc": a.offer_ctc,
            "offer_letter_url": a.offer_letter_url,
            "has_resume": a.resume_id is not None,
            "resume_snapshot": a.resume_snapshot,
        })

    return output


@router.post(
    "/{job_id}/rounds/advance",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Bulk Advance Candidates to Next Drive Round",
)
async def advance_applicants_round(
    job_id: uuid.UUID,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Advance selected candidates to the next drive round (e.g. from OA to Technical Interview)."""
    from app.models.application import Application, ApplicationEvent, ApplicationStatus
    from app.models.notification import Notification, NotificationType

    app_ids = [uuid.UUID(i) for i in payload.get("application_ids", [])]
    target_round = payload.get("target_round", 2)
    target_status = payload.get("target_status", ApplicationStatus.SHORTLISTED.value)
    note = payload.get("note", f"Advanced to Round {target_round}")

    if not app_ids:
        return {"updated_count": 0, "message": "No application IDs provided."}

    from sqlalchemy import select
    res = await db.execute(select(Application).where(Application.id.in_(app_ids)))
    apps = list(res.scalars().all())

    updated = 0
    for a in apps:
        a.current_round = target_round
        a.status = target_status
        updated += 1

        db.add(
            ApplicationEvent(
                application_id=a.id,
                status=target_status,
                actor="RECRUITER" if current_user.role == "RECRUITER" else "TPO",
                note=note,
            )
        )

        db.add(
            Notification(
                user_id=a.user_id,
                type=NotificationType.PLACEMENT,
                title="Placement Drive Round Update 🎉",
                message=f"Congratulations! You have been advanced to Round {target_round}: {note}",
            )
        )

    await db.commit()
    return {"updated_count": updated, "message": f"Successfully advanced {updated} candidates to Round {target_round}."}


@router.post(
    "/{job_id}/offers",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Release Digital Placement Offer",
)
async def release_offer(
    job_id: uuid.UUID,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Release official job offer to candidate with CTC details."""
    from app.models.application import Application, ApplicationEvent, ApplicationStatus
    from app.models.notification import Notification, NotificationType

    app_id = uuid.UUID(payload.get("application_id"))
    ctc = payload.get("ctc", "₹12 LPA")
    offer_letter_url = payload.get("offer_letter_url")

    application = await db.get(Application, app_id)
    if not application:
        return {"error": "Application not found"}

    application.status = ApplicationStatus.OFFERED.value
    application.offer_ctc = ctc
    application.offer_letter_url = offer_letter_url

    db.add(
        ApplicationEvent(
            application_id=application.id,
            status=ApplicationStatus.OFFERED.value,
            actor="RECRUITER" if current_user.role == "RECRUITER" else "TPO",
            note=f"Official job offer extended with CTC {ctc}.",
        )
    )

    db.add(
        Notification(
            user_id=application.user_id,
            type=NotificationType.PLACEMENT,
            title="OFFICIAL JOB OFFER RECEIVED! 🏆",
            message=f"Congratulations! You have been extended a placement offer with CTC package of {ctc}.",
        )
    )

    await db.commit()
    return {"message": f"Offer extended to candidate with CTC {ctc}.", "application_id": str(app_id)}


@router.post(
    "/{job_id}/applicants/shortlist-csv",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Batch Shortlist Candidates via CSV Email Roster",
)
async def shortlist_candidates_csv(
    job_id: uuid.UUID,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Batch advance candidates matching a CSV/Excel list of candidate emails."""
    from app.models.application import Application, ApplicationEvent, ApplicationStatus
    from app.models.notification import Notification, NotificationType
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    emails = [e.strip().lower() for e in payload.get("emails", []) if e.strip()]
    target_round = payload.get("target_round", 2)
    note = payload.get("note", "Shortlisted via Recruiter Assessment Roster")

    if not emails:
        return {"matched_count": 0, "message": "No emails provided."}

    res = await db.execute(
        select(Application)
        .where(Application.job_id == job_id)
        .options(selectinload(Application.user))
    )
    apps = list(res.scalars().all())

    matched_emails = []
    unmatched_emails = set(emails)

    for a in apps:
        if a.user and a.user.email.lower() in emails:
            a.current_round = target_round
            a.status = ApplicationStatus.SHORTLISTED.value
            matched_emails.append(a.user.email)
            unmatched_emails.discard(a.user.email.lower())

            db.add(
                ApplicationEvent(
                    application_id=a.id,
                    status=ApplicationStatus.SHORTLISTED.value,
                    actor="RECRUITER",
                    note=note,
                )
            )
            db.add(
                Notification(
                    user_id=a.user_id,
                    type=NotificationType.PLACEMENT,
                    title=f"Shortlisted for Round {target_round}! 🎯",
                    message=f"You have been shortlisted for Round {target_round}: {note}",
                )
            )

    await db.commit()
    return {
        "matched_count": len(matched_emails),
        "advanced_emails": matched_emails,
        "unmatched_count": len(unmatched_emails),
        "unmatched_emails": list(unmatched_emails),
        "message": f"Successfully shortlisted {len(matched_emails)} candidates for Round {target_round}.",
    }



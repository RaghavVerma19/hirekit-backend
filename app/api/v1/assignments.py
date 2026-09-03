from datetime import datetime, timezone
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.assignment import Assignment, AssignmentSubmission, SubmissionStatus
from app.models.user import Role, User
from app.schemas.assignment import (
    AssignmentCreateIn,
    AssignmentGradeIn,
    AssignmentOut,
    AssignmentSubmissionOut,
    AssignmentSubmitIn,
)
from app.schemas.common import MessageOut

router = APIRouter(prefix='/assignments', tags=['Assignments & Coursework'])


@router.get('', response_model=List[AssignmentOut], status_code=status.HTTP_200_OK)
async def list_assignments(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[AssignmentOut]:
    result = await db.execute(select(Assignment).order_by(desc(Assignment.due_at)))
    assignments = list(result.scalars().all())

    # Fetch current user submissions
    sub_res = await db.execute(
        select(AssignmentSubmission).where(AssignmentSubmission.student_id == current_user.id)
    )
    user_subs = {s.assignment_id: s for s in sub_res.scalars().all()}

    output = []
    for a in assignments:
        out = AssignmentOut.model_validate(a)
        if a.id in user_subs:
            out.my_submission = AssignmentSubmissionOut.model_validate(user_subs[a.id])
        output.append(out)
    return output


@router.post('', response_model=AssignmentOut, status_code=status.HTTP_201_CREATED)
async def create_assignment(
    body: AssignmentCreateIn,
    current_user: User = Depends(require_role([Role.ADMIN, Role.TPO])),
    db: AsyncSession = Depends(get_db),
) -> AssignmentOut:
    assignment = Assignment(
        title=body.title,
        description=body.description,
        course_code=body.course_code,
        due_at=body.due_at,
        max_score=body.max_score,
        target_department=body.target_department,
        target_batch=body.target_batch,
        attachment_url=body.attachment_url,
        created_by=current_user.id,
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)
    return AssignmentOut.model_validate(assignment)


@router.post('/{assignment_id}/submit', response_model=AssignmentSubmissionOut, status_code=status.HTTP_201_CREATED)
async def submit_assignment(
    assignment_id: uuid.UUID,
    body: AssignmentSubmitIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AssignmentSubmissionOut:
    assignment = await db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Assignment not found')

    existing_sub = await db.execute(
        select(AssignmentSubmission).where(
            AssignmentSubmission.assignment_id == assignment_id,
            AssignmentSubmission.student_id == current_user.id,
        )
    )
    sub = existing_sub.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    is_late = now > assignment.due_at

    if sub:
        sub.file_url = body.file_url
        sub.submitted_at = now
        sub.status = SubmissionStatus.LATE if is_late else SubmissionStatus.SUBMITTED
    else:
        sub = AssignmentSubmission(
            assignment_id=assignment_id,
            student_id=current_user.id,
            file_url=body.file_url,
            submitted_at=now,
            status=SubmissionStatus.LATE if is_late else SubmissionStatus.SUBMITTED,
        )
        db.add(sub)

    await db.commit()
    await db.refresh(sub)
    return AssignmentSubmissionOut.model_validate(sub)

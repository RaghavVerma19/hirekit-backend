from datetime import datetime, timezone
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.competition import Competition, CompetitionRegistration
from app.models.user import Role, User
from app.schemas.common import MessageOut
from app.schemas.competition import (
    CompetitionCreateIn,
    CompetitionOut,
    CompetitionRegisterIn,
    CompetitionRegistrationOut,
)
from app.models.education import Education

router = APIRouter(prefix='/competitions', tags=['Campus Competitions & Hackathons'])


@router.get('', response_model=List[CompetitionOut], status_code=status.HTTP_200_OK)
async def list_competitions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[CompetitionOut]:
    result = await db.execute(select(Competition).order_by(desc(Competition.end_date)))
    competitions = list(result.scalars().all())

    reg_result = await db.execute(
        select(CompetitionRegistration.competition_id).where(
            CompetitionRegistration.user_id == current_user.id
        )
    )
    registered_ids = set(reg_result.scalars().all())

    output = []
    for c in competitions:
        out = CompetitionOut.model_validate(c)
        out.is_registered = c.id in registered_ids
        output.append(out)
    return output


@router.post('', response_model=CompetitionOut, status_code=status.HTTP_201_CREATED)
async def create_competition(
    body: CompetitionCreateIn,
    current_user: User = Depends(require_role([Role.ADMIN, Role.TPO])),
    db: AsyncSession = Depends(get_db),
) -> CompetitionOut:
    comp = Competition(
        title=body.title,
        description=body.description,
        category=body.category,
        start_date=body.start_date,
        end_date=body.end_date,
        prize_pool=body.prize_pool,
        max_participants=body.max_participants,
        rules_url=body.rules_url,
        created_by=current_user.id,
    )
    db.add(comp)
    await db.commit()
    await db.refresh(comp)
    return CompetitionOut.model_validate(comp)


@router.post('/{competition_id}/register', response_model=MessageOut, status_code=status.HTTP_200_OK)
async def register_competition(
    competition_id: uuid.UUID,
    body: CompetitionRegisterIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    comp = await db.get(Competition, competition_id)
    if not comp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Competition not found')

    existing = await db.execute(
        select(CompetitionRegistration).where(
            CompetitionRegistration.competition_id == competition_id,
            CompetitionRegistration.user_id == current_user.id,
        )
    )
    if existing.scalar_one_or_none():
        return MessageOut(message='Already registered for this competition')

    if comp.max_participants and comp.participant_count >= comp.max_participants:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Competition is at full capacity')

    reg = CompetitionRegistration(
        competition_id=competition_id,
        user_id=current_user.id,
        team_name=body.team_name,
    )
    db.add(reg)
    comp.participant_count += 1
    await db.commit()
    return MessageOut(message='Successfully registered for competition')


@router.get('/{competition_id}/registrations', response_model=List[CompetitionRegistrationOut], status_code=status.HTTP_200_OK)
async def list_competition_registrations(
    competition_id: uuid.UUID,
    current_user: User = Depends(require_role([Role.ADMIN, Role.TPO])),
    db: AsyncSession = Depends(get_db),
) -> List[CompetitionRegistrationOut]:
    comp = await db.get(Competition, competition_id)
    if not comp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Competition not found')

    result = await db.execute(
        select(CompetitionRegistration, User, Education)
        .join(User, CompetitionRegistration.user_id == User.id)
        .outerjoin(Education, Education.user_id == User.id)
        .where(CompetitionRegistration.competition_id == competition_id)
        .order_by(desc(CompetitionRegistration.registered_at))
    )
    rows = result.all()

    seen_registrations = set()
    output = []
    for reg, user, edu in rows:
        if reg.id in seen_registrations:
            continue
        seen_registrations.add(reg.id)
        output.append(
            CompetitionRegistrationOut(
                id=reg.id,
                competition_id=reg.competition_id,
                user_id=reg.user_id,
                team_name=reg.team_name,
                registered_at=reg.registered_at,
                user_name=user.name,
                user_email=user.email,
                user_department=edu.department if edu else None,
                user_batch=str(edu.end_year) if (edu and edu.end_year) else None,
            )
        )
    return output

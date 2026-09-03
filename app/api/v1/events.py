from datetime import datetime, timezone
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.event import CollegeEvent, EventRegistration
from app.models.user import Role, User
from app.schemas.common import MessageOut
from app.schemas.event import EventCreateIn, EventOut, EventUpdateIn

router = APIRouter(prefix='/events', tags=['College Events'])


@router.get('', response_model=List[EventOut], status_code=status.HTTP_200_OK)
async def list_events(
    event_type: Optional[str] = Query(None),
    upcoming_only: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[EventOut]:
    query = select(CollegeEvent).order_by(desc(CollegeEvent.date))
    if upcoming_only:
        query = query.where(CollegeEvent.date >= datetime.now(timezone.utc))

    result = await db.execute(query)
    events = list(result.scalars().all())

    # Check user registrations
    reg_result = await db.execute(
        select(EventRegistration.event_id).where(EventRegistration.user_id == current_user.id)
    )
    registered_event_ids = set(reg_result.scalars().all())

    output = []
    for ev in events:
        out = EventOut.model_validate(ev)
        out.is_registered = ev.id in registered_event_ids
        output.append(out)
    return output


@router.get('/{event_id}', response_model=EventOut, status_code=status.HTTP_200_OK)
async def get_event(
    event_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EventOut:
    ev = await db.get(CollegeEvent, event_id)
    if not ev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Event not found')

    reg = await db.execute(
        select(EventRegistration).where(
            EventRegistration.event_id == event_id,
            EventRegistration.user_id == current_user.id,
        )
    )
    is_reg = reg.scalar_one_or_none() is not None

    out = EventOut.model_validate(ev)
    out.is_registered = is_reg
    return out


@router.post('', response_model=EventOut, status_code=status.HTTP_201_CREATED)
async def create_event(
    body: EventCreateIn,
    current_user: User = Depends(require_role([Role.ADMIN, Role.TPO])),
    db: AsyncSession = Depends(get_db),
) -> EventOut:
    new_event = CollegeEvent(
        title=body.title,
        description=body.description,
        event_type=body.event_type,
        date=body.date,
        end_date=body.end_date,
        location=body.location,
        is_virtual=body.is_virtual,
        meeting_url=body.meeting_url,
        organizer_id=current_user.id,
        organizer_name=current_user.name or 'Placement Cell',
        banner_url=body.banner_url,
        max_attendees=body.max_attendees,
    )
    db.add(new_event)
    await db.commit()
    await db.refresh(new_event)
    return EventOut.model_validate(new_event)


@router.put('/{event_id}', response_model=EventOut, status_code=status.HTTP_200_OK)
async def update_event(
    event_id: uuid.UUID,
    body: EventUpdateIn,
    current_user: User = Depends(require_role([Role.ADMIN, Role.TPO])),
    db: AsyncSession = Depends(get_db),
) -> EventOut:
    ev = await db.get(CollegeEvent, event_id)
    if not ev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Event not found')

    update_data = body.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(ev, k, v)

    await db.commit()
    await db.refresh(ev)
    return EventOut.model_validate(ev)


@router.delete('/{event_id}', response_model=MessageOut, status_code=status.HTTP_200_OK)
async def delete_event(
    event_id: uuid.UUID,
    current_user: User = Depends(require_role([Role.ADMIN, Role.TPO])),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    ev = await db.get(CollegeEvent, event_id)
    if not ev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Event not found')

    await db.delete(ev)
    await db.commit()
    return MessageOut(message='Event deleted successfully')


@router.post('/{event_id}/register', response_model=MessageOut, status_code=status.HTTP_200_OK)
async def register_event(
    event_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    ev = await db.get(CollegeEvent, event_id)
    if not ev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Event not found')

    existing = await db.execute(
        select(EventRegistration).where(
            EventRegistration.event_id == event_id,
            EventRegistration.user_id == current_user.id,
        )
    )
    if existing.scalar_one_or_none():
        return MessageOut(message='Already registered for this event')

    if ev.max_attendees and ev.registered_count >= ev.max_attendees:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Event is fully booked')

    reg = EventRegistration(event_id=event_id, user_id=current_user.id)
    db.add(reg)
    ev.registered_count += 1
    await db.commit()
    return MessageOut(message='Successfully registered for event')


@router.delete('/{event_id}/register', response_model=MessageOut, status_code=status.HTTP_200_OK)
async def unregister_event(
    event_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    ev = await db.get(CollegeEvent, event_id)
    if not ev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Event not found')

    existing = await db.execute(
        select(EventRegistration).where(
            EventRegistration.event_id == event_id,
            EventRegistration.user_id == current_user.id,
        )
    )
    reg = existing.scalar_one_or_none()
    if not reg:
        return MessageOut(message='Not registered for this event')

    await db.delete(reg)
    if ev.registered_count > 0:
        ev.registered_count -= 1
    await db.commit()
    return MessageOut(message='Successfully unregistered from event')

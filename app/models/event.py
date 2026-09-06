from datetime import datetime, timezone
import enum
from typing import List, Optional
import uuid
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class EventType(str, enum.Enum):
    WORKSHOP = 'workshop'
    SEMINAR = 'seminar'
    HACKATHON = 'hackathon'
    CAREER_FAIR = 'career_fair'
    INFO_SESSION = 'info_session'
    OTHER = 'other'


class CollegeEvent(Base):
    __tablename__ = 'college_events'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    college_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('colleges.id', ondelete='CASCADE'), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default='', nullable=False)
    event_type: Mapped[EventType] = mapped_column(
        Enum(EventType, name='event_type_enum'), default=EventType.WORKSHOP, nullable=False
    )
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    location: Mapped[str] = mapped_column(String(255), default='Campus Auditorium', nullable=False)
    is_virtual: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    meeting_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    organizer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True
    )
    organizer_name: Mapped[str] = mapped_column(String(100), default='Training and Placement Cell', nullable=False)
    banner_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    max_attendees: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    registered_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    registrations: Mapped[List['EventRegistration']] = relationship(
        'EventRegistration', back_populates='event', cascade='all, delete-orphan'
    )
    college: Mapped['College'] = relationship('College', back_populates='events')


class EventRegistration(Base):
    __tablename__ = 'event_registrations'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('college_events.id', ondelete='CASCADE'), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    event: Mapped['CollegeEvent'] = relationship('CollegeEvent', back_populates='registrations')
    user: Mapped['User'] = relationship('User')

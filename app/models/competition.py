from datetime import datetime, timezone
import enum
from typing import List, Optional
import uuid
from sqlalchemy import (
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


class CompetitionStatus(str, enum.Enum):
    UPCOMING = 'upcoming'
    ACTIVE = 'active'
    CLOSING_SOON = 'closing-soon'
    COMPLETED = 'completed'


class Competition(Base):
    __tablename__ = 'competitions'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    college_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('colleges.id', ondelete='CASCADE'), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default='', nullable=False)
    category: Mapped[str] = mapped_column(String(100), default='Coding and Algorithms', nullable=False)
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    prize_pool: Mapped[str] = mapped_column(String(100), default='Cash Prizes + Certificates', nullable=False)
    status: Mapped[CompetitionStatus] = mapped_column(
        Enum(CompetitionStatus, name='competition_status_enum'),
        default=CompetitionStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    max_participants: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    participant_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rules_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    registrations: Mapped[List['CompetitionRegistration']] = relationship(
        'CompetitionRegistration', back_populates='competition', cascade='all, delete-orphan'
    )
    college: Mapped['College'] = relationship('College', back_populates='competitions')


class CompetitionRegistration(Base):
    __tablename__ = 'competition_registrations'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    competition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('competitions.id', ondelete='CASCADE'), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True
    )
    team_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    competition: Mapped['Competition'] = relationship('Competition', back_populates='registrations')
    user: Mapped['User'] = relationship('User')

from datetime import datetime, timezone
import enum
from typing import List, Optional
import uuid
from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class SubmissionStatus(str, enum.Enum):
    SUBMITTED = 'submitted'
    GRADED = 'graded'
    LATE = 'late'


class Assignment(Base):
    __tablename__ = 'assignments'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default='', nullable=False)
    course_code: Mapped[str] = mapped_column(String(50), default='CS301', nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    max_score: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True
    )
    target_department: Mapped[str] = mapped_column(String(100), default='Computer Science', nullable=False)
    target_batch: Mapped[str] = mapped_column(String(50), default='2026', nullable=False)
    attachment_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    submissions: Mapped[List['AssignmentSubmission']] = relationship(
        'AssignmentSubmission', back_populates='assignment', cascade='all, delete-orphan'
    )


class AssignmentSubmission(Base):
    __tablename__ = 'assignment_submissions'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('assignments.id', ondelete='CASCADE'), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True
    )
    file_url: Mapped[str] = mapped_column(String(512), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus, name='submission_status_enum'),
        default=SubmissionStatus.SUBMITTED,
        nullable=False,
    )
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    assignment: Mapped['Assignment'] = relationship('Assignment', back_populates='submissions')
    student: Mapped['User'] = relationship('User')

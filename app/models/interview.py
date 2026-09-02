from datetime import datetime
import enum
from typing import Optional
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


class InterviewStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    RESCHEDULED = "RESCHEDULED"


class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="SET NULL"), nullable=True
    )
    company_name: Mapped[str] = mapped_column(String(150), nullable=False)
    role_title: Mapped[str] = mapped_column(String(150), nullable=False)
    round_name: Mapped[str] = mapped_column(String(100), default="Technical Round 1", nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    meeting_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[InterviewStatus] = mapped_column(
        Enum(InterviewStatus, name="interview_status_enum"),
        default=InterviewStatus.SCHEDULED,
        nullable=False,
    )
    prep_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="interviews")
    application: Mapped[Optional["Application"]] = relationship("Application")

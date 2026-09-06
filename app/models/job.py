from datetime import datetime, timezone
import enum
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class JobType(str, enum.Enum):
    FULL_TIME = "Full-time"
    INTERNSHIP = "Internship"
    PART_TIME = "Part-time"
    CONTRACT = "Contract"


class JobStatus(str, enum.Enum):
    OPEN = "open"
    CLOSING_SOON = "closing-soon"
    CLOSED = "closed"


class JobTier(str, enum.Enum):
    REGULAR = "REGULAR"
    DREAM = "DREAM"
    SUPER_DREAM = "SUPER_DREAM"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    college_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("colleges.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    company_logo: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    location: Mapped[str] = mapped_column(String(150), default="Hybrid / On-site", nullable=False)
    type: Mapped[JobType] = mapped_column(
        Enum(JobType, native_enum=False), default=JobType.FULL_TIME, nullable=False
    )
    tier: Mapped[JobTier] = mapped_column(
        Enum(JobTier, native_enum=False), default=JobTier.REGULAR, nullable=False, index=True
    )
    ctc: Mapped[str] = mapped_column(String(100), default="Best in Industry", nullable=False)
    min_cgpa: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    max_active_backlogs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    min_10th_marks: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    min_12th_marks: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    eligible_departments: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    eligible_batches: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    skills: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    requirements: Mapped[str] = mapped_column(Text, default="", nullable=False)
    rounds: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    is_drive_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False), default=JobStatus.OPEN, nullable=False, index=True
    )
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    posted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    applications: Mapped[List["Application"]] = relationship(
        "Application", back_populates="job", cascade="all, delete-orphan"
    )
    college: Mapped["College"] = relationship("College", back_populates="jobs")

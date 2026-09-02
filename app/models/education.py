from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class Education(Base):
    __tablename__ = "educations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    degree: Mapped[str] = mapped_column(String(100), nullable=False)
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    institution: Mapped[str] = mapped_column(String(255), nullable=False)
    start_year: Mapped[int] = mapped_column(Integer, nullable=False)
    end_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cgpa: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    percentage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    marksheet_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    semester_scores: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSON, default=list)
    education_gap: Mapped[Optional[int]] = mapped_column(Integer, default=0, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="educations")

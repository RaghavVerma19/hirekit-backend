from datetime import datetime, timezone
from typing import Any, Dict, Optional
import uuid
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(150), default="My Resume", nullable=False)
    pdf_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    template_id: Mapped[str] = mapped_column(String(50), default="modern-tech", nullable=False)
    content_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False, index=True)
    ats_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    ats_feedback: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    leaderboard_eligible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="resumes")

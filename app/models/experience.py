from datetime import date, datetime, timezone
from typing import List, Optional
import uuid
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class Experience(Base):
    __tablename__ = "experiences"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(100), nullable=False)
    company: Mapped[str] = mapped_column(String(100), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    type: Mapped[str] = mapped_column(String(50), default="INTERNSHIP", nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    certificate_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="experiences")
    responsibilities: Mapped[List["Responsibility"]] = relationship(
        "Responsibility",
        back_populates="experience",
        cascade="all, delete-orphan",
        order_by="Responsibility.order_index",
    )


class Responsibility(Base):
    __tablename__ = "responsibilities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    experience_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("experiences.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    experience: Mapped["Experience"] = relationship(
        "Experience", back_populates="responsibilities"
    )

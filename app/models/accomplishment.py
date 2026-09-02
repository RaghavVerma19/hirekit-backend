from datetime import date, datetime
import enum
from typing import Any, Dict, Optional
import uuid
from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    JSON,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class AccomplishmentType(str, enum.Enum):
    CERTIFICATE = "CERTIFICATE"
    AWARD = "AWARD"
    COMPETITION = "COMPETITION"
    PUBLICATION = "PUBLICATION"
    PATENT = "PATENT"
    WORKSHOP = "WORKSHOP"
    VOLUNTEERING = "VOLUNTEERING"
    OTHER = "OTHER"


class Accomplishment(Base):
    __tablename__ = "accomplishments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[AccomplishmentType] = mapped_column(
        Enum(AccomplishmentType, name="accomplishment_type_enum", native_enum=False),
        default=AccomplishmentType.CERTIFICATE,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    issuer: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    issue_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    credential_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    document_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="accomplishments")

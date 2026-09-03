import uuid
from sqlalchemy import (
    Boolean,
    Float,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class PlacementPolicy(Base):
    __tablename__ = "placement_policies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    college_name: Mapped[str] = mapped_column(
        String(200), default="Poornima University", nullable=False
    )
    dream_tier_threshold_lpa: Mapped[float] = mapped_column(
        Float, default=6.0, nullable=False
    )
    super_dream_tier_threshold_lpa: Mapped[float] = mapped_column(
        Float, default=12.0, nullable=False
    )
    max_offers_allowed: Mapped[int] = mapped_column(
        Integer, default=2, nullable=False
    )
    single_offer_rule: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    lock_on_super_dream: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    max_backlogs_allowed_default: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

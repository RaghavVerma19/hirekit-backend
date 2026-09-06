from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy import (
    Boolean,
    DateTime,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class College(Base):
    __tablename__ = "colleges"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    domain: Mapped[Optional[str]] = mapped_column(String(150), unique=True, nullable=True)

    # Custom Institutional Branding
    logo_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    banner_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    primary_color: Mapped[str] = mapped_column(String(20), default="#3B48E0", nullable=False)
    accent_color: Mapped[str] = mapped_column(String(20), default="#7C3AED", nullable=False)

    # Dynamic Feature Flags, Placement Rules & Academic Setup
    settings: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=lambda: {
            "features": {
                "assignments": True,
                "competitions": True,
                "events": True,
                "linkedin_audit": True,
                "resume_leaderboard": True,
                "community_feed": True,
                "mock_interviews": True,
                "ai_cover_letter": True,
                "alumni_network": True,
                "recruiter_direct_messaging": False,
            },
            "placement_rules": {
                "allow_multiple_offers": False,
                "max_offers": 1,
                "pydream_upgrade_allowed": True,
                "min_cgpa_cutoff_default": 6.0,
                "max_backlogs_allowed": 0,
                "dream_tier_threshold_lpa": 6.0,
                "super_dream_tier_threshold_lpa": 12.0,
                "strict_single_offer_policy": True,
                "debar_on_unexcused_absence": True,
            },
            "academic": {
                "departments": [
                    "Computer Science & Engineering",
                    "Information Technology",
                    "Electronics & Communication",
                    "Electrical Engineering",
                    "Mechanical Engineering",
                    "Civil Engineering",
                ],
                "batches": ["2023", "2024", "2025", "2026", "2027"],
                "grading_scale": "10.0",
                "current_academic_year": "2025-2026",
            },
            "accreditation": {
                "nirf_reporting_enabled": True,
                "naac_reporting_enabled": True,
                "affiliating_university": "",
                "aicte_code": "",
            },
            "security": {
                "mfa_enforced_for_staff": False,
                "allow_student_self_registration": True,
                "require_admin_approval_for_registration": False,
                "auto_notify_drive_updates": True,
            },
        },
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Tenant Relationships
    users: Mapped[List["User"]] = relationship(
        "User", back_populates="college", cascade="all, delete-orphan"
    )
    jobs: Mapped[List["Job"]] = relationship(
        "Job", back_populates="college", cascade="all, delete-orphan"
    )
    events: Mapped[List["CollegeEvent"]] = relationship(
        "CollegeEvent", back_populates="college", cascade="all, delete-orphan"
    )
    competitions: Mapped[List["Competition"]] = relationship(
        "Competition", back_populates="college", cascade="all, delete-orphan"
    )
    assignments: Mapped[List["Assignment"]] = relationship(
        "Assignment", back_populates="college", cascade="all, delete-orphan"
    )
    posts: Mapped[List["Post"]] = relationship(
        "Post", back_populates="college", cascade="all, delete-orphan"
    )

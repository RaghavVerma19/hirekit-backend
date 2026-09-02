"""jobs_and_applications

Revision ID: 004_jobs_and_applications
Revises: 003_dashboard_resumes
Create Date: 2026-09-02 22:42:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "004_jobs_and_applications"
down_revision: Union[str, None] = "003_dashboard_resumes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Jobs Table
    op.create_table(
        "jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("company_name", sa.String(length=150), nullable=False),
        sa.Column("company_logo", sa.String(length=512), nullable=True),
        sa.Column("location", sa.String(length=150), nullable=False, server_default="Hybrid / On-site"),
        sa.Column("type", sa.Enum("Full-time", "Internship", "Part-time", "Contract", name="job_type_enum", native_enum=False), nullable=False),
        sa.Column("ctc", sa.String(length=100), nullable=False, server_default="Best in Industry"),
        sa.Column("min_cgpa", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("eligible_departments", sa.JSON(), nullable=False),
        sa.Column("eligible_batches", sa.JSON(), nullable=False),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("requirements", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.Enum("open", "closing-soon", "closed", name="job_status_enum", native_enum=False), nullable=False, server_default="open"),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    op.create_index(op.f("ix_jobs_title"), "jobs", ["title"], unique=False)
    op.create_index(op.f("ix_jobs_company_name"), "jobs", ["company_name"], unique=False)
    op.create_index(op.f("ix_jobs_status"), "jobs", ["status"], unique=False)
    op.create_index(op.f("ix_jobs_deadline"), "jobs", ["deadline"], unique=False)

    # 2. Applications Table
    op.create_table(
        "applications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("resume_id", sa.UUID(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "APPLIED", "UNDER_REVIEW", "SHORTLISTED", "INTERVIEW_SCHEDULED", "OFFERED", "REJECTED", "WITHDRAWN",
                name="application_status_enum",
                native_enum=False,
            ),
            nullable=False,
            server_default="APPLIED",
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], name=op.f("fk_applications_job_id_jobs"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_applications_user_id_users"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resume_id"], ["resumes.id"], name=op.f("fk_applications_resume_id_resumes"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applications")),
        sa.UniqueConstraint("user_id", "job_id", name="uq_user_job_application"),
    )
    op.create_index(op.f("ix_applications_job_id"), "applications", ["job_id"], unique=False)
    op.create_index(op.f("ix_applications_user_id"), "applications", ["user_id"], unique=False)
    op.create_index(op.f("ix_applications_status"), "applications", ["status"], unique=False)

    # 3. Application Events Table
    op.create_table(
        "application_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "APPLIED", "UNDER_REVIEW", "SHORTLISTED", "INTERVIEW_SCHEDULED", "OFFERED", "REJECTED", "WITHDRAWN",
                name="application_status_enum",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("actor", sa.String(length=50), nullable=False, server_default="STUDENT"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], name=op.f("fk_application_events_application_id_applications"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_events")),
    )
    op.create_index(op.f("ix_application_events_application_id"), "application_events", ["application_id"], unique=False)


def downgrade() -> None:
    op.drop_table("application_events")
    op.drop_table("applications")
    op.drop_table("jobs")

"""notifications_and_admin

Revision ID: 005_notifications_admin
Revises: 004_jobs_and_applications
Create Date: 2026-09-02 22:48:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "005_notifications_admin"
down_revision: Union[str, None] = "004_jobs_and_applications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Notifications Table
    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "type",
            sa.Enum("PLACEMENT", "INTERVIEW", "SYSTEM", "COMMUNITY", name="notification_type_enum", native_enum=False),
            nullable=False,
            server_default="PLACEMENT",
        ),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("link", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_notifications_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index(op.f("ix_notifications_user_id"), "notifications", ["user_id"], unique=False)
    op.create_index(op.f("ix_notifications_is_read"), "notifications", ["is_read"], unique=False)
    op.create_index(op.f("ix_notifications_created_at"), "notifications", ["created_at"], unique=False)

    # 2. Interviews Table
    op.create_table(
        "interviews",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=True),
        sa.Column("company_name", sa.String(length=150), nullable=False),
        sa.Column("role_title", sa.String(length=150), nullable=False),
        sa.Column("round_name", sa.String(length=100), nullable=False, server_default="Technical Round 1"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("meeting_url", sa.String(length=512), nullable=True),
        sa.Column(
            "status",
            sa.Enum("SCHEDULED", "COMPLETED", "CANCELLED", "RESCHEDULED", name="interview_status_enum", native_enum=False),
            nullable=False,
            server_default="SCHEDULED",
        ),
        sa.Column("prep_score", sa.Integer(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_interviews_user_id_users"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], name=op.f("fk_interviews_application_id_applications"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interviews")),
    )
    op.create_index(op.f("ix_interviews_user_id"), "interviews", ["user_id"], unique=False)
    op.create_index(op.f("ix_interviews_scheduled_at"), "interviews", ["scheduled_at"], unique=False)

    # 3. Audit Logs Table
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("target_id", sa.String(length=100), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], name=op.f("fk_audit_logs_actor_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(op.f("ix_audit_logs_actor_id"), "audit_logs", ["actor_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_action"), "audit_logs", ["action"], unique=False)
    op.create_index(op.f("ix_audit_logs_created_at"), "audit_logs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("interviews")
    op.drop_table("notifications")

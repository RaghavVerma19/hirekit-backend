"""missing events competitions assignments

Revision ID: 006_missing_events
Revises: 60bde5b1fb1a
Create Date: 2026-09-06 20:00:00.000000

Creates the 6 tables that models expect but no migration ever created:
college_events, event_registrations, competitions, competition_registrations,
assignments, assignment_submissions. Created WITHOUT college_id — 007 adds it.
All enums use native_enum=False (VARCHAR, no PG TYPE).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006_missing_events"
down_revision: Union[str, None] = "60bde5b1fb1a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return table in insp.get_table_names()


def upgrade() -> None:
    # 1. college_events (no college_id yet — 007 adds it)
    if not _table_exists("college_events"):
        op.create_table(
            "college_events",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "event_type",
                sa.Enum("workshop", "seminar", "hackathon", "career_fair", "info_session", "other", name="event_type_enum", native_enum=False),
                nullable=False,
                server_default="workshop",
            ),
            sa.Column("date", sa.DateTime(timezone=True), nullable=False),
            sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("location", sa.String(length=255), nullable=False, server_default="Campus Auditorium"),
            sa.Column("is_virtual", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("meeting_url", sa.String(length=512), nullable=True),
            sa.Column("organizer_id", sa.UUID(), nullable=True),
            sa.Column("organizer_name", sa.String(length=100), nullable=False, server_default="Training and Placement Cell"),
            sa.Column("banner_url", sa.String(length=512), nullable=True),
            sa.Column("max_attendees", sa.Integer(), nullable=True),
            sa.Column("registered_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["organizer_id"], ["users.id"], name=op.f("fk_college_events_organizer_id_users"), ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_college_events")),
        )
        op.create_index(op.f("ix_college_events_title"), "college_events", ["title"], unique=False)
        op.create_index(op.f("ix_college_events_date"), "college_events", ["date"], unique=False)

    # 2. event_registrations
    if not _table_exists("event_registrations"):
        op.create_table(
            "event_registrations",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("event_id", sa.UUID(), nullable=False),
            sa.Column("user_id", sa.UUID(), nullable=False),
            sa.Column("registered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["event_id"], ["college_events.id"], name=op.f("fk_event_registrations_event_id_college_events"), ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_event_registrations_user_id_users"), ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_event_registrations")),
        )
        op.create_index(op.f("ix_event_registrations_event_id"), "event_registrations", ["event_id"], unique=False)
        op.create_index(op.f("ix_event_registrations_user_id"), "event_registrations", ["user_id"], unique=False)

    # 3. competitions (no college_id yet — 007 adds it)
    if not _table_exists("competitions"):
        op.create_table(
            "competitions",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("category", sa.String(length=100), nullable=False, server_default="Coding and Algorithms"),
            sa.Column("start_date", sa.DateTime(timezone=True), nullable=False),
            sa.Column("end_date", sa.DateTime(timezone=True), nullable=False),
            sa.Column("prize_pool", sa.String(length=100), nullable=False, server_default="Cash Prizes + Certificates"),
            sa.Column(
                "status",
                sa.Enum("upcoming", "active", "closing-soon", "completed", name="competition_status_enum", native_enum=False),
                nullable=False,
                server_default="active",
            ),
            sa.Column("max_participants", sa.Integer(), nullable=True),
            sa.Column("participant_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("rules_url", sa.String(length=512), nullable=True),
            sa.Column("created_by", sa.UUID(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_competitions_created_by_users"), ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_competitions")),
        )
        op.create_index(op.f("ix_competitions_title"), "competitions", ["title"], unique=False)
        op.create_index(op.f("ix_competitions_end_date"), "competitions", ["end_date"], unique=False)
        op.create_index(op.f("ix_competitions_status"), "competitions", ["status"], unique=False)

    # 4. competition_registrations
    if not _table_exists("competition_registrations"):
        op.create_table(
            "competition_registrations",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("competition_id", sa.UUID(), nullable=False),
            sa.Column("user_id", sa.UUID(), nullable=False),
            sa.Column("team_name", sa.String(length=100), nullable=True),
            sa.Column("registered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], name=op.f("fk_competition_registrations_competition_id_competitions"), ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_competition_registrations_user_id_users"), ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_competition_registrations")),
        )
        op.create_index(op.f("ix_competition_registrations_competition_id"), "competition_registrations", ["competition_id"], unique=False)
        op.create_index(op.f("ix_competition_registrations_user_id"), "competition_registrations", ["user_id"], unique=False)

    # 5. assignments (no college_id yet — 007 adds it)
    if not _table_exists("assignments"):
        op.create_table(
            "assignments",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("course_code", sa.String(length=50), nullable=False, server_default="CS301"),
            sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("max_score", sa.Float(), nullable=False, server_default="100.0"),
            sa.Column("created_by", sa.UUID(), nullable=True),
            sa.Column("target_department", sa.String(length=100), nullable=False, server_default="Computer Science"),
            sa.Column("target_batch", sa.String(length=50), nullable=False, server_default="2026"),
            sa.Column("attachment_url", sa.String(length=512), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_assignments_created_by_users"), ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_assignments")),
        )
        op.create_index(op.f("ix_assignments_title"), "assignments", ["title"], unique=False)
        op.create_index(op.f("ix_assignments_due_at"), "assignments", ["due_at"], unique=False)

    # 6. assignment_submissions
    if not _table_exists("assignment_submissions"):
        op.create_table(
            "assignment_submissions",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("assignment_id", sa.UUID(), nullable=False),
            sa.Column("student_id", sa.UUID(), nullable=False),
            sa.Column("file_url", sa.String(length=512), nullable=False),
            sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column(
                "status",
                sa.Enum("submitted", "graded", "late", name="submission_status_enum", native_enum=False),
                nullable=False,
                server_default="submitted",
            ),
            sa.Column("score", sa.Float(), nullable=True),
            sa.Column("feedback", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["assignment_id"], ["assignments.id"], name=op.f("fk_assignment_submissions_assignment_id_assignments"), ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["student_id"], ["users.id"], name=op.f("fk_assignment_submissions_student_id_users"), ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_assignment_submissions")),
        )
        op.create_index(op.f("ix_assignment_submissions_assignment_id"), "assignment_submissions", ["assignment_id"], unique=False)
        op.create_index(op.f("ix_assignment_submissions_student_id"), "assignment_submissions", ["student_id"], unique=False)


def downgrade() -> None:
    for tbl in ("assignment_submissions", "assignments", "competition_registrations", "competitions", "event_registrations", "college_events"):
        if _table_exists(tbl):
            op.drop_table(tbl)

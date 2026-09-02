"""profile_models

Revision ID: 002_profile_models
Revises: 001_initial_auth
Create Date: 2026-09-02 19:35:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002_profile_models"
down_revision: Union[str, None] = "001_initial_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Educations table
    op.create_table(
        "educations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("degree", sa.String(length=100), nullable=False),
        sa.Column("department", sa.String(length=100), nullable=True),
        sa.Column("institution", sa.String(length=255), nullable=False),
        sa.Column("start_year", sa.Integer(), nullable=False),
        sa.Column("end_year", sa.Integer(), nullable=True),
        sa.Column("cgpa", sa.Float(), nullable=True),
        sa.Column("percentage", sa.Float(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("marksheet_url", sa.String(length=512), nullable=True),
        sa.Column("semester_scores", sa.JSON(), nullable=True),
        sa.Column("education_gap", sa.Integer(), nullable=True, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_educations_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_educations")),
    )
    op.create_index(op.f("ix_educations_user_id"), "educations", ["user_id"], unique=False)

    # 2. Experiences table
    op.create_table(
        "experiences",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=100), nullable=False),
        sa.Column("company", sa.String(length=100), nullable=False),
        sa.Column("location", sa.String(length=100), nullable=True),
        sa.Column("type", sa.String(length=50), nullable=False, server_default="INTERNSHIP"),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("certificate_url", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_experiences_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_experiences")),
    )
    op.create_index(op.f("ix_experiences_user_id"), "experiences", ["user_id"], unique=False)

    # 3. Responsibilities table
    op.create_table(
        "responsibilities",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("experience_id", sa.UUID(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(
            ["experience_id"],
            ["experiences.id"],
            name=op.f("fk_responsibilities_experience_id_experiences"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_responsibilities")),
    )
    op.create_index(
        op.f("ix_responsibilities_experience_id"),
        "responsibilities",
        ["experience_id"],
        unique=False,
    )

    # 4. User Skills table
    op.create_table(
        "user_skills",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("level", sa.String(length=50), nullable=False, server_default="INTERMEDIATE"),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_skills_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_skills")),
        sa.UniqueConstraint("user_id", "name", name=op.f("uq_user_skill_name")),
    )
    op.create_index(op.f("ix_user_skills_user_id"), "user_skills", ["user_id"], unique=False)

    # 5. Projects table
    op.create_table(
        "projects",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("live_url", sa.String(length=512), nullable=True),
        sa.Column("github_url", sa.String(length=512), nullable=True),
        sa.Column("skills_used", sa.JSON(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("is_ongoing", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_projects_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
    )
    op.create_index(op.f("ix_projects_user_id"), "projects", ["user_id"], unique=False)

    # 6. Accomplishments table
    op.create_table(
        "accomplishments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "CERTIFICATE",
                "AWARD",
                "COMPETITION",
                "PUBLICATION",
                "PATENT",
                "WORKSHOP",
                "VOLUNTEERING",
                "OTHER",
                name="accomplishment_type_enum",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("issuer", sa.String(length=150), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("credential_url", sa.String(length=512), nullable=True),
        sa.Column("document_url", sa.String(length=512), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_accomplishments_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accomplishments")),
    )
    op.create_index(op.f("ix_accomplishments_user_id"), "accomplishments", ["user_id"], unique=False)

    # 7. Guardians table
    op.create_table(
        "guardians",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("relationship", sa.String(length=50), nullable=False, server_default="FATHER"),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("occupation", sa.String(length=100), nullable=True),
        sa.Column("annual_income", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_guardians_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_guardians")),
    )
    op.create_index(op.f("ix_guardians_user_id"), "guardians", ["user_id"], unique=False)

    # 8. Social Links table
    op.create_table(
        "social_links",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("url", sa.String(length=512), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_social_links_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_social_links")),
    )
    op.create_index(op.f("ix_social_links_user_id"), "social_links", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_table("social_links")
    op.drop_table("guardians")
    op.drop_table("accomplishments")
    op.drop_table("projects")
    op.drop_table("user_skills")
    op.drop_table("responsibilities")
    op.drop_table("experiences")
    op.drop_table("educations")

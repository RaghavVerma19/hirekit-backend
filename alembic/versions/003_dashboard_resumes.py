"""dashboard_and_resumes

Revision ID: 003_dashboard_resumes
Revises: 002_profile_models
Create Date: 2026-09-02 20:05:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "003_dashboard_resumes"
down_revision: Union[str, None] = "002_profile_models"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Posts table
    op.create_table(
        "posts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=False),
        sa.Column("author_name", sa.String(length=100), nullable=False),
        sa.Column("author_avatar", sa.String(length=512), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("likes_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("comments_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
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
            ["author_id"],
            ["users.id"],
            name=op.f("fk_posts_author_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_posts")),
    )
    op.create_index(op.f("ix_posts_author_id"), "posts", ["author_id"], unique=False)
    op.create_index(op.f("ix_posts_created_at"), "posts", ["created_at"], unique=False)

    # 2. Post Comments table
    op.create_table(
        "post_comments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("post_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=False),
        sa.Column("author_name", sa.String(length=100), nullable=False),
        sa.Column("author_avatar", sa.String(length=512), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_post_comments_author_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["posts.id"],
            name=op.f("fk_post_comments_post_id_posts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_post_comments")),
    )
    op.create_index(op.f("ix_post_comments_author_id"), "post_comments", ["author_id"], unique=False)
    op.create_index(op.f("ix_post_comments_post_id"), "post_comments", ["post_id"], unique=False)

    # 3. Resumes table
    op.create_table(
        "resumes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=150), nullable=False, server_default="My Resume"),
        sa.Column("pdf_url", sa.String(length=512), nullable=True),
        sa.Column("template_id", sa.String(length=50), nullable=False, server_default="modern-tech"),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("ats_score", sa.Integer(), nullable=True),
        sa.Column("ats_feedback", sa.JSON(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("leaderboard_eligible", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
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
            name=op.f("fk_resumes_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resumes")),
    )
    op.create_index(op.f("ix_resumes_user_id"), "resumes", ["user_id"], unique=False)
    op.create_index(op.f("ix_resumes_content_hash"), "resumes", ["content_hash"], unique=False)
    op.create_index(op.f("ix_resumes_ats_score"), "resumes", ["ats_score"], unique=False)


def downgrade() -> None:
    op.drop_table("resumes")
    op.drop_table("post_comments")
    op.drop_table("posts")

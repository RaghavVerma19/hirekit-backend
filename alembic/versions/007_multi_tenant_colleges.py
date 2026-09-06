"""multi_tenant_colleges

Revision ID: 007_multi_tenant_colleges
Revises: 60bde5b1fb1a
Create Date: 2026-09-06 19:30:00.000000

"""
from typing import Sequence, Union
import json
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = '007_multi_tenant_colleges'
down_revision: Union[str, None] = '60bde5b1fb1a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_COLLEGE_ID = '00000000-0000-0000-0000-000000000001'

def upgrade() -> None:
    # 1. Create colleges table
    op.create_table(
        'colleges',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('domain', sa.String(length=150), nullable=True),
        sa.Column('logo_url', sa.String(length=512), nullable=True),
        sa.Column('banner_url', sa.String(length=512), nullable=True),
        sa.Column('primary_color', sa.String(length=20), server_default='#3B48E0', nullable=False),
        sa.Column('accent_color', sa.String(length=20), server_default='#7C3AED', nullable=False),
        sa.Column('settings', sa.JSON(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(op.f('ix_colleges_slug'), 'colleges', ['slug'], unique=True)
    op.create_index(op.f('ix_colleges_code'), 'colleges', ['code'], unique=True)
    op.create_index(op.f('ix_colleges_domain'), 'colleges', ['domain'], unique=True)

    # 2. Seed default college (Poornima University)
    default_settings = json.dumps({
        "features": {
            "assignments": True,
            "competitions": True,
            "events": True,
            "linkedin_audit": True,
            "resume_leaderboard": True,
            "community_feed": True,
        },
        "placement_rules": {
            "allow_multiple_offers": False,
            "max_offers": 1,
            "pydream_upgrade_allowed": True,
            "min_cgpa_cutoff_default": 6.0,
            "max_backlogs_allowed": 0,
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
        },
    })

    op.execute(
        f"""
        INSERT INTO colleges (id, name, slug, code, domain, primary_color, accent_color, settings, is_active)
        VALUES ('{DEFAULT_COLLEGE_ID}', 'Poornima University', 'poornima', 'PU-JAIPUR', 'poornima.edu.in', '#3B48E0', '#7C3AED', '{default_settings}', true)
        ON CONFLICT (id) DO NOTHING;
        """
    )

    # 3. Add college_id to users
    op.add_column('users', sa.Column('college_id', UUID(as_uuid=True), nullable=True))
    op.create_index(op.f('ix_users_college_id'), 'users', ['college_id'], unique=False)
    op.create_foreign_key('fk_users_college_id_colleges', 'users', 'colleges', ['college_id'], ['id'], ondelete='CASCADE')
    op.execute(f"UPDATE users SET college_id = '{DEFAULT_COLLEGE_ID}' WHERE college_id IS NULL;")

    # 4. Add college_id to jobs
    op.add_column('jobs', sa.Column('college_id', UUID(as_uuid=True), nullable=True))
    op.create_index(op.f('ix_jobs_college_id'), 'jobs', ['college_id'], unique=False)
    op.create_foreign_key('fk_jobs_college_id_colleges', 'jobs', 'colleges', ['college_id'], ['id'], ondelete='CASCADE')
    op.execute(f"UPDATE jobs SET college_id = '{DEFAULT_COLLEGE_ID}' WHERE college_id IS NULL;")
    op.alter_column('jobs', 'college_id', nullable=False)

    # 5. Add college_id to college_events
    op.add_column('college_events', sa.Column('college_id', UUID(as_uuid=True), nullable=True))
    op.create_index(op.f('ix_college_events_college_id'), 'college_events', ['college_id'], unique=False)
    op.create_foreign_key('fk_college_events_college_id_colleges', 'college_events', 'colleges', ['college_id'], ['id'], ondelete='CASCADE')
    op.execute(f"UPDATE college_events SET college_id = '{DEFAULT_COLLEGE_ID}' WHERE college_id IS NULL;")
    op.alter_column('college_events', 'college_id', nullable=False)

    # 6. Add college_id to competitions
    op.add_column('competitions', sa.Column('college_id', UUID(as_uuid=True), nullable=True))
    op.create_index(op.f('ix_competitions_college_id'), 'competitions', ['college_id'], unique=False)
    op.create_foreign_key('fk_competitions_college_id_colleges', 'competitions', 'colleges', ['college_id'], ['id'], ondelete='CASCADE')
    op.execute(f"UPDATE competitions SET college_id = '{DEFAULT_COLLEGE_ID}' WHERE college_id IS NULL;")
    op.alter_column('competitions', 'college_id', nullable=False)

    # 7. Add college_id to assignments
    op.add_column('assignments', sa.Column('college_id', UUID(as_uuid=True), nullable=True))
    op.create_index(op.f('ix_assignments_college_id'), 'assignments', ['college_id'], unique=False)
    op.create_foreign_key('fk_assignments_college_id_colleges', 'assignments', 'colleges', ['college_id'], ['id'], ondelete='CASCADE')
    op.execute(f"UPDATE assignments SET college_id = '{DEFAULT_COLLEGE_ID}' WHERE college_id IS NULL;")
    op.alter_column('assignments', 'college_id', nullable=False)

    # 8. Add college_id to posts
    op.add_column('posts', sa.Column('college_id', UUID(as_uuid=True), nullable=True))
    op.create_index(op.f('ix_posts_college_id'), 'posts', ['college_id'], unique=False)
    op.create_foreign_key('fk_posts_college_id_colleges', 'posts', 'colleges', ['college_id'], ['id'], ondelete='CASCADE')
    op.execute(f"UPDATE posts SET college_id = '{DEFAULT_COLLEGE_ID}' WHERE college_id IS NULL;")
    op.alter_column('posts', 'college_id', nullable=False)


def downgrade() -> None:
    op.drop_constraint('fk_posts_college_id_colleges', 'posts', type_='foreignkey')
    op.drop_index(op.f('ix_posts_college_id'), table_name='posts')
    op.drop_column('posts', 'college_id')

    op.drop_constraint('fk_assignments_college_id_colleges', 'assignments', type_='foreignkey')
    op.drop_index(op.f('ix_assignments_college_id'), table_name='assignments')
    op.drop_column('assignments', 'college_id')

    op.drop_constraint('fk_competitions_college_id_colleges', 'competitions', type_='foreignkey')
    op.drop_index(op.f('ix_competitions_college_id'), table_name='competitions')
    op.drop_column('competitions', 'college_id')

    op.drop_constraint('fk_college_events_college_id_colleges', 'college_events', type_='foreignkey')
    op.drop_index(op.f('ix_college_events_college_id'), table_name='college_events')
    op.drop_column('college_events', 'college_id')

    op.drop_constraint('fk_jobs_college_id_colleges', 'jobs', type_='foreignkey')
    op.drop_index(op.f('ix_jobs_college_id'), table_name='jobs')
    op.drop_column('jobs', 'college_id')

    op.drop_constraint('fk_users_college_id_colleges', 'users', type_='foreignkey')
    op.drop_index(op.f('ix_users_college_id'), table_name='users')
    op.drop_column('users', 'college_id')

    op.drop_index(op.f('ix_colleges_domain'), table_name='colleges')
    op.drop_index(op.f('ix_colleges_code'), table_name='colleges')
    op.drop_index(op.f('ix_colleges_slug'), table_name='colleges')
    op.drop_table('colleges')

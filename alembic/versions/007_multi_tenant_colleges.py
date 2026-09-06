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
down_revision: Union[str, None] = '006_missing_events'
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

    # 3-8. Add college_id to tenant tables (idempotent: skip if table/column missing)
    for _table in ('users', 'jobs', 'college_events', 'competitions', 'assignments', 'posts'):
        _insp = sa.inspect(op.get_bind())
        if _table not in _insp.get_table_names():
            continue
        _cols = [c['name'] for c in _insp.get_columns(_table)]
        if 'college_id' in _cols:
            continue
        op.add_column(_table, sa.Column('college_id', UUID(as_uuid=True), nullable=True))
        op.create_index(op.f(f'ix_{_table}_college_id'), _table, ['college_id'], unique=False)
        op.create_foreign_key(f'fk_{_table}_college_id_colleges', _table, 'colleges', ['college_id'], ['id'], ondelete='CASCADE')
        op.execute(f"UPDATE {_table} SET college_id = '{DEFAULT_COLLEGE_ID}' WHERE college_id IS NULL;")
        op.alter_column(_table, 'college_id', nullable=False)


def downgrade() -> None:
    _insp = sa.inspect(op.get_bind())
    _tables = _insp.get_table_names()
    for _table in ('posts', 'assignments', 'competitions', 'college_events', 'jobs', 'users'):
        if _table not in _tables:
            continue
        _cols = [c['name'] for c in _insp.get_columns(_table)]
        if 'college_id' not in _cols:
            continue
        try:
            op.drop_constraint(f'fk_{_table}_college_id_colleges', _table, type_='foreignkey')
        except Exception:
            pass
        try:
            op.drop_index(op.f(f'ix_{_table}_college_id'), table_name=_table)
        except Exception:
            pass
        op.drop_column(_table, 'college_id')

    op.drop_index(op.f('ix_colleges_domain'), table_name='colleges')
    op.drop_index(op.f('ix_colleges_code'), table_name='colleges')
    op.drop_index(op.f('ix_colleges_slug'), table_name='colleges')
    op.drop_table('colleges')

"""add_report_definitions_table

Revision ID: d74a7f323ec9
Revises: ae0494b24fa6
Create Date: 2026-08-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'd74a7f323ec9'
down_revision: Union[str, None] = 'ae0494b24fa6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'report_definitions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), server_default=''),
        sa.Column('view_name', sa.String(100), nullable=False),
        sa.Column('columns', sa.JSON(), server_default='[]'),
        sa.Column('filters', sa.JSON(), server_default='[]'),
        sa.Column('sort_by', sa.String(100), server_default=''),
        sa.Column('sort_order', sa.String(4), server_default='asc'),
        sa.Column('limit', sa.Integer(), server_default='100'),
        sa.Column('schedule_cron', sa.String(50), nullable=True),
        sa.Column('export_format', sa.String(20), server_default='csv'),
        sa.Column('owner_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('tags', sa.JSON(), server_default='[]'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('report_definitions')

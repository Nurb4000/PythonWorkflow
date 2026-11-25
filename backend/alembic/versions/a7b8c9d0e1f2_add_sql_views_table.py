"""add sql_views table

Revision ID: a7b8c9d0e1f2
Revises: b1c2a14cd999
Create Date: 2026-10-16

The SQLView model lived in Base.metadata but was never emitted into a
migration, so a fresh database had no sql_views table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'b1c2a14cd999'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'sql_views',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), server_default=''),
        sa.Column('definition_sql', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_sql_views_name', 'sql_views', ['name'])
    op.create_index('ix_sql_views_id', 'sql_views', ['id'])


def downgrade() -> None:
    op.drop_index('ix_sql_views_name', table_name='sql_views')
    op.drop_index('ix_sql_views_id', table_name='sql_views')
    op.drop_table('sql_views')

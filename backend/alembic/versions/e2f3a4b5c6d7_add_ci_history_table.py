"""add ci_history table for CMDB audit trail

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-08-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = 'e2f3a4b5c6d7'
down_revision: Union[str, None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    insp = inspect(conn)
    return table_name in insp.get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    conn = op.get_bind()
    insp = inspect(conn)
    indexes = insp.get_indexes(table_name)
    return any(idx['name'] == index_name for idx in indexes)


def upgrade() -> None:
    if not _table_exists('ci_history'):
        op.create_table(
            'ci_history',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('ci_id', sa.Integer(), nullable=False),
            sa.Column('changed_by', sa.Integer(), nullable=True),
            sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('field_key', sa.String(length=100), nullable=True),
            sa.Column('old_value', sa.JSON(), nullable=True),
            sa.Column('new_value', sa.JSON(), nullable=True),
            sa.Column('change_type', sa.String(length=20), nullable=False, server_default='update'),
            sa.ForeignKeyConstraint(['ci_id'], ['configuration_items.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['changed_by'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )

    if _table_exists('ci_history'):
        for idx in [
            ('ix_ci_history_id', 'ci_history', ['id']),
            ('idx_ci_history_ci_id', 'ci_history', ['ci_id']),
            ('idx_ci_history_changed_at', 'ci_history', ['changed_at']),
        ]:
            if not _index_exists(idx[1], idx[0]):
                op.create_index(idx[0], idx[1], idx[2], unique=False)


def downgrade() -> None:
    op.drop_index('idx_ci_history_changed_at', table_name='ci_history')
    op.drop_index('idx_ci_history_ci_id', table_name='ci_history')
    op.drop_index('ix_ci_history_id', table_name='ci_history')
    op.drop_table('ci_history')

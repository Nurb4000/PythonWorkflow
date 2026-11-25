"""add password_changed_at to users for user-scoped access-token revocation

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-11-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = 'm3n4o5p6q7r8'
down_revision: Union[str, None] = 'l2m3n4o5p6q7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    insp = inspect(conn)
    return column_name in [c['name'] for c in insp.get_columns(table_name)]


def upgrade() -> None:
    if not _column_exists('users', 'password_changed_at'):
        op.add_column(
            'users',
            sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    op.drop_column('users', 'password_changed_at')

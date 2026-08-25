"""add_pause_state_to_tasks

Revision ID: 6af62d011f28
Revises: d74a7f323ec9
Create Date: 2026-08-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '6af62d011f28'
down_revision: Union[str, None] = 'd74a7f323ec9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tasks', sa.Column('pause_state', sa.String(50), server_default='in_process'))


def downgrade() -> None:
    op.drop_column('tasks', 'pause_state')

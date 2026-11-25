"""add_ola_tracking_columns_to_tasks

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-08-12 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e0f1a2b3c4d5'
down_revision: Union[str, None] = 'd9e0f1a2b3c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tasks', sa.Column('priority', sa.Integer(), nullable=True))
    op.add_column('tasks', sa.Column('ola_pickup_target_hours', sa.Integer(), nullable=True))
    op.add_column('tasks', sa.Column('ola_closure_target_hours', sa.Integer(), nullable=True))
    op.add_column('tasks', sa.Column('ola_pickup_met', sa.Boolean(), nullable=True))
    op.add_column('tasks', sa.Column('ola_closure_met', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('tasks', 'ola_closure_met')
    op.drop_column('tasks', 'ola_pickup_met')
    op.drop_column('tasks', 'ola_closure_target_hours')
    op.drop_column('tasks', 'ola_pickup_target_hours')
    op.drop_column('tasks', 'priority')

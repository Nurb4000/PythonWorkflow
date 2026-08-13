"""add_sla_tracking_columns_to_workflow_runs

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-08-12 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c8d9e0f1a2b3'
down_revision: Union[str, None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('workflow_runs', sa.Column('sla_response_target_hours', sa.Integer(), nullable=True))
    op.add_column('workflow_runs', sa.Column('sla_resolution_target_hours', sa.Integer(), nullable=True))
    op.add_column('workflow_runs', sa.Column('sla_response_met', sa.Boolean(), nullable=True))
    op.add_column('workflow_runs', sa.Column('sla_resolution_met', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('workflow_runs', 'sla_resolution_met')
    op.drop_column('workflow_runs', 'sla_response_met')
    op.drop_column('workflow_runs', 'sla_resolution_target_hours')
    op.drop_column('workflow_runs', 'sla_response_target_hours')

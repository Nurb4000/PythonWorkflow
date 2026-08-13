"""add_priority_and_service_id_to_workflow_runs

Revision ID: b7c8d9e0f1a2
Revises: a3671d8c9ed2
Create Date: 2026-08-12 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, None] = 'a3671d8c9ed2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add priority column to workflow_runs (SERVICE_MANAGEMENT_PLAN Phase 3)
    op.add_column(
        'workflow_runs',
        sa.Column('priority', sa.Integer(), nullable=True)
    )

    # Add service_id column to workflow_runs (SERVICE_MANAGEMENT_PLAN Phase 4)
    op.add_column(
        'workflow_runs',
        sa.Column('service_id', sa.Integer(), sa.ForeignKey('services.id'), nullable=True)
    )
    op.create_index(op.f('ix_workflow_runs_service_id'), 'workflow_runs', ['service_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_workflow_runs_service_id'), table_name='workflow_runs')
    op.drop_column('workflow_runs', 'service_id')
    op.drop_column('workflow_runs', 'priority')

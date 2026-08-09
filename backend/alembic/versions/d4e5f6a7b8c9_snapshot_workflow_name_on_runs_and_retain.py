"""Snapshot workflow name on runs and retain runs when a workflow is deleted

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Snapshot the workflow name on each run so historical runs stay
    # identifiable even after the workflow is deleted.
    op.add_column(
        'workflow_runs',
        sa.Column('workflow_name', sa.String(length=255), server_default='', nullable=False),
    )
    # Backfill the snapshot from the current workflows.
    op.execute(
        """
        UPDATE workflow_runs
        SET workflow_name = COALESCE((SELECT name FROM workflows WHERE workflows.id = workflow_runs.workflow_id), '')
        """
    )

    # Retain runs when a workflow is deleted: workflow_runs.workflow_id
    # becomes NULL instead of cascading the rows away.
    op.drop_constraint('workflow_runs_workflow_id_fkey', 'workflow_runs', type_='foreignkey')
    op.alter_column('workflow_runs', 'workflow_id', existing_type=sa.Integer(), nullable=True)
    op.create_foreign_key(
        'workflow_runs_workflow_id_fkey', 'workflow_runs', 'workflows',
        ['workflow_id'], ['id'], ondelete='SET NULL',
    )

    # Keep step instances as history too: step_id becomes NULL when a step
    # is removed.
    op.drop_constraint('step_instances_step_id_fkey', 'step_instances', type_='foreignkey')
    op.alter_column('step_instances', 'step_id', existing_type=sa.Integer(), nullable=True)
    op.create_foreign_key(
        'step_instances_step_id_fkey', 'step_instances', 'workflow_steps',
        ['step_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('step_instances_step_id_fkey', 'step_instances', type_='foreignkey')
    op.alter_column('step_instances', 'step_id', existing_type=sa.Integer(), nullable=False)
    op.create_foreign_key(
        'step_instances_step_id_fkey', 'step_instances', 'workflow_steps',
        ['step_id'], ['id'],
    )

    op.drop_constraint('workflow_runs_workflow_id_fkey', 'workflow_runs', type_='foreignkey')
    op.alter_column('workflow_runs', 'workflow_id', existing_type=sa.Integer(), nullable=False)
    op.create_foreign_key(
        'workflow_runs_workflow_id_fkey', 'workflow_runs', 'workflows',
        ['workflow_id'], ['id'],
    )

    op.drop_column('workflow_runs', 'workflow_name')

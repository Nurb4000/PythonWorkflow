"""Add date_targets table for calendar-based deadline tracking

Revision ID: a1b2c3d4d5e6
Revises: e0f1a2b3c4d5
Create Date: 2026-08-13 00:00:00.000000

INCIDENT_CHANGE_PLAN Phase 0.1 — supports change management target dates
and any workflow that needs absolute calendar deadlines rather than
relative SLA/OLA hour windows.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4d5e6'
down_revision: Union[str, None] = 'e0f1a2b3c4d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "date_targets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("workflow_run_id", sa.Integer(), sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_id", sa.Integer(), sa.ForeignKey("workflow_steps.id", ondelete="SET NULL"), nullable=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("target_key", sa.String(100), nullable=False),
        sa.Column("target_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("custom_data", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_date_targets_id", "date_targets", ["id"])
    op.create_index("ix_date_targets_workflow_run_id", "date_targets", ["workflow_run_id"])
    op.create_index("ix_date_targets_target_key", "date_targets", ["target_key"])
    op.create_index("ix_date_targets_target_datetime", "date_targets", ["target_datetime"])
    op.create_index("idx_date_targets_status_pending", "date_targets", ["status", "target_datetime"])


def downgrade() -> None:
    op.drop_index("idx_date_targets_status_pending", "date_targets")
    op.drop_index("ix_date_targets_target_datetime", "date_targets")
    op.drop_index("ix_date_targets_target_key", "date_targets")
    op.drop_index("ix_date_targets_workflow_run_id", "date_targets")
    op.drop_index("ix_date_targets_id", "date_targets")
    op.drop_table("date_targets")

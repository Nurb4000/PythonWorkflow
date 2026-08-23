"""add is_active columns for soft delete support

Revision ID: a1b2c3d4e5f6_soft_delete
Revises: f6a7b8c9d0e1_add_step_metadata_snapshot_on_instances
Create Date: 2026-08-17

Adds is_active columns to configuration_items, ci_relationships, tasks, and date_targets
to support soft-delete (deactivation) instead of hard deletion for audit/historical tracking.
"""
from alembic import op
import sqlalchemy as sa


revision = 'g7h8i9j0k1l2'
down_revision = 'a1b2c3d4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('configuration_items', sa.Column('is_active', sa.Boolean(), nullable=True, server_default=sa.text('true')))
    op.add_column('ci_relationships', sa.Column('is_active', sa.Boolean(), nullable=True, server_default=sa.text('true')))
    op.add_column('tasks', sa.Column('is_active', sa.Boolean(), nullable=True, server_default=sa.text('true')))
    op.add_column('date_targets', sa.Column('is_active', sa.Boolean(), nullable=True, server_default=sa.text('true')))


def downgrade():
    op.drop_column('date_targets', 'is_active')
    op.drop_column('tasks', 'is_active')
    op.drop_column('ci_relationships', 'is_active')
    op.drop_column('configuration_items', 'is_active')

"""add email_processing_log table for IMAP monitor

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'email_processing_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email_uid', sa.String(length=100), nullable=False),
        sa.Column('workflow_id', sa.Integer(), nullable=True),
        sa.Column('run_id', sa.Integer(), nullable=True),
        sa.Column('email_from', sa.String(length=500), nullable=False, server_default=''),
        sa.Column('email_subject', sa.Text(), nullable=False, server_default=''),
        sa.Column('rule_tag', sa.String(length=50), nullable=False, server_default=''),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=False, server_default=''),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id']),
        sa.ForeignKeyConstraint(['run_id'], ['workflow_runs.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_email_processing_log_id', 'email_processing_log', ['id'], unique=False)
    op.create_index('ix_email_processing_log_email_uid', 'email_processing_log', ['email_uid'], unique=False)
    op.create_index('idx_email_uid_workflow', 'email_processing_log', ['email_uid', 'workflow_id'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_email_uid_workflow', table_name='email_processing_log')
    op.drop_index('ix_email_processing_log_email_uid', table_name='email_processing_log')
    op.drop_index('ix_email_processing_log_id', table_name='email_processing_log')
    op.drop_table('email_processing_log')

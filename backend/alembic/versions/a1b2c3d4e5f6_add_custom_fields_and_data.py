"""add custom fields and custom_data columns

Revision ID: a1b2c3d4e5f6
Revises: 33c1a9f5fe6d
Create Date: 2026-08-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '33c1a9f5fe6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'custom_field_definitions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('field_key', sa.String(length=100), nullable=False),
        sa.Column('label', sa.String(length=255), nullable=False),
        sa.Column('field_type', sa.String(length=50), nullable=False),
        sa.Column('target_table', sa.String(length=100), nullable=False),
        sa.Column('scope', sa.String(length=20), nullable=False, server_default='global'),
        sa.Column('scope_id', sa.Integer(), nullable=True),
        sa.Column('config', sa.JSON(), nullable=True, server_default='{}'),
        sa.Column('is_required', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_custom_field_definitions_id', 'custom_field_definitions', ['id'], unique=False)
    op.create_index('ix_custom_field_definitions_target_table', 'custom_field_definitions', ['target_table'], unique=False)
    op.create_unique_constraint(
        'uq_custom_field_key_scope',
        'custom_field_definitions',
        ['field_key', 'target_table', 'scope', 'scope_id']
    )

    # Add custom_data JSON column to existing tables (idempotent)
    tables_to_extend = ['tasks', 'workflow_runs', 'step_instances', 'users', 'groups', 'form_submissions']
    for table in tables_to_extend:
        conn = op.get_bind()
        has_col = conn.execute(sa.text(
            f"SELECT COUNT(*) FROM information_schema.columns WHERE table_name = '{table}' AND column_name = 'custom_data'"
        )).scalar()
        if not has_col:
            op.add_column(table, sa.Column('custom_data', sa.JSON(), nullable=True, server_default='{}'))


def downgrade() -> None:
    for table in ['tasks', 'workflow_runs', 'step_instances', 'users', 'groups', 'form_submissions']:
        op.drop_column(table, 'custom_data')

    op.drop_constraint('uq_custom_field_key_scope', 'custom_field_definitions', type_='unique')
    op.drop_index('ix_custom_field_definitions_target_table', table_name='custom_field_definitions')
    op.drop_index('ix_custom_field_definitions_id', table_name='custom_field_definitions')
    op.drop_table('custom_field_definitions')

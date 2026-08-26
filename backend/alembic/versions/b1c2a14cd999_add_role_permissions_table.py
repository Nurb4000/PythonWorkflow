"""add_role_permissions_table

Revision ID: b1c2a14cd999
Revises: f9cef82800d6
Create Date: 2026-08-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b1c2a14cd999'
down_revision: Union[str, None] = 'f9cef82800d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'role_permissions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('role_id', sa.Integer(), sa.ForeignKey('custom_roles.id'), nullable=False),
        sa.Column('table_name', sa.String(100), nullable=False),
        sa.Column('can_view', sa.Boolean(), server_default='true'),
        sa.Column('can_edit', sa.Boolean(), server_default='false'),
        sa.Column('can_delete', sa.Boolean(), server_default='false'),
        sa.Column('visible_fields', sa.JSON(), server_default='[]'),
        sa.Column('editable_fields', sa.JSON(), server_default='[]'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_role_permissions_role_table', 'role_permissions', ['role_id', 'table_name'])


def downgrade() -> None:
    op.drop_index('ix_role_permissions_role_table', table_name='role_permissions')
    op.drop_table('role_permissions')

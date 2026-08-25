"""add_field_definitions_table

Revision ID: 7d66f11b8ee2
Revises: f8c81f0ad2d3
Create Date: 2026-08-25 10:37:34.225756

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d66f11b8ee2'
down_revision: Union[str, None] = 'f8c81f0ad2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'field_definitions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('key', sa.String(100), nullable=False, unique=True),
        sa.Column('label', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), server_default=''),
        sa.Column('field_type', sa.String(50), nullable=False, server_default='string'),
        sa.Column('options', sa.JSON(), server_default='[]'),
        sa.Column('validation_rules', sa.JSON(), server_default='{}'),
        sa.Column('help_text', sa.Text(), server_default=''),
        sa.Column('owner_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True, index=True),
        sa.Column('tags', sa.JSON(), server_default='[]'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('is_deprecated', sa.Boolean(), server_default='false'),
        sa.Column('deprecated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deprecated_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_field_definitions_key', 'field_definitions', ['key'])


def downgrade() -> None:
    op.drop_index('ix_field_definitions_key', table_name='field_definitions')
    op.drop_table('field_definitions')

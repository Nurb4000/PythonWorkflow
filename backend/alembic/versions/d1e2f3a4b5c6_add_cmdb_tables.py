"""add cmdb tables: ci_types, configuration_items, ci_relationships

Revision ID: d1e2f3a4b5c6
Revises: c3d4e5f6a7b8
Create Date: 2026-08-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    insp = inspect(conn)
    return table_name in insp.get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    conn = op.get_bind()
    insp = inspect(conn)
    indexes = insp.get_indexes(table_name)
    return any(idx['name'] == index_name for idx in indexes)


def upgrade() -> None:
    # --- ci_types ---
    if not _table_exists('ci_types'):
        op.create_table(
            'ci_types',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('key', sa.String(length=50), nullable=False),
            sa.Column('description', sa.Text(), server_default=''),
            sa.Column('icon', sa.String(length=50), server_default=''),
            sa.Column('field_schema', sa.JSON(), server_default='[]'),
            sa.Column('is_active', sa.Boolean(), server_default='1'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('name'),
            sa.UniqueConstraint('key'),
        )

    if _table_exists('ci_types'):
        for idx in [
            ('ix_ci_types_id', 'ci_types', ['id']),
            ('ix_ci_types_name', 'ci_types', ['name']),
            ('ix_ci_types_key', 'ci_types', ['key']),
        ]:
            if not _index_exists(idx[1], idx[0]):
                op.create_index(idx[0], idx[1], idx[2], unique=False)

    # --- configuration_items ---
    if not _table_exists('configuration_items'):
        op.create_table(
            'configuration_items',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('type_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('status', sa.String(length=30), server_default='active'),
            sa.Column('ci_data', sa.JSON(), server_default='{}'),
            sa.Column('custom_data', sa.JSON(), server_default='{}'),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.Column('updated_by', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['type_id'], ['ci_types.id']),
            sa.ForeignKeyConstraint(['created_by'], ['users.id']),
            sa.ForeignKeyConstraint(['updated_by'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )

    if _table_exists('configuration_items'):
        for idx in [
            ('ix_configuration_items_id', 'configuration_items', ['id']),
            ('ix_configuration_items_type_id', 'configuration_items', ['type_id']),
            ('ix_configuration_items_name', 'configuration_items', ['name']),
            ('idx_configuration_items_type_status', 'configuration_items', ['type_id', 'status']),
        ]:
            if not _index_exists(idx[1], idx[0]):
                op.create_index(idx[0], idx[1], idx[2], unique=False)

    # --- ci_relationships ---
    if not _table_exists('ci_relationships'):
        op.create_table(
            'ci_relationships',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('source_ci_id', sa.Integer(), nullable=False),
            sa.Column('target_ci_id', sa.Integer(), nullable=False),
            sa.Column('relationship_type', sa.String(length=50), nullable=False),
            sa.Column('description', sa.Text(), server_default=''),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['source_ci_id'], ['configuration_items.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['target_ci_id'], ['configuration_items.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )

    if _table_exists('ci_relationships'):
        for idx in [
            ('ix_ci_relationships_id', 'ci_relationships', ['id']),
            ('idx_ci_relationships_source', 'ci_relationships', ['source_ci_id']),
            ('idx_ci_relationships_target', 'ci_relationships', ['target_ci_id']),
        ]:
            if not _index_exists(idx[1], idx[0]):
                op.create_index(idx[0], idx[1], idx[2], unique=False)


def downgrade() -> None:
    op.drop_index('idx_ci_relationships_target', table_name='ci_relationships')
    op.drop_index('idx_ci_relationships_source', table_name='ci_relationships')
    op.drop_index('ix_ci_relationships_id', table_name='ci_relationships')
    op.drop_table('ci_relationships')

    op.drop_index('idx_configuration_items_type_status', table_name='configuration_items')
    op.drop_index('ix_configuration_items_name', table_name='configuration_items')
    op.drop_index('ix_configuration_items_type_id', table_name='configuration_items')
    op.drop_index('ix_configuration_items_id', table_name='configuration_items')
    op.drop_table('configuration_items')

    op.drop_index('ix_ci_types_key', table_name='ci_types')
    op.drop_index('ix_ci_types_name', table_name='ci_types')
    op.drop_index('ix_ci_types_id', table_name='ci_types')
    op.drop_table('ci_types')

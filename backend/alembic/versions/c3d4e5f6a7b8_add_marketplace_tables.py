"""add marketplace_items and saved_node_templates tables

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
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
    if not _table_exists('marketplace_items'):
        op.create_table(
            'marketplace_items',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('item_type', sa.String(length=20), nullable=False),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('description', sa.Text(), server_default=''),
            sa.Column('category', sa.String(length=100), server_default='General'),
            sa.Column('tags', sa.Text(), server_default='[]'),
            sa.Column('author_id', sa.Integer(), nullable=False),
            sa.Column('version', sa.Integer(), server_default='1'),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('content_format', sa.String(length=10), nullable=False),
            sa.Column('node_type', sa.String(length=50), nullable=True),
            sa.Column('status', sa.String(length=20), server_default='published'),
            sa.Column('is_active', sa.Boolean(), server_default='1'),
            sa.Column('downloads_count', sa.Integer(), server_default='0'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['author_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )

    if _table_exists('marketplace_items'):
        for idx in [
            ('ix_marketplace_items_id', 'marketplace_items', ['id']),
            ('ix_marketplace_items_name', 'marketplace_items', ['name']),
            ('idx_marketplace_items_type_status', 'marketplace_items', ['item_type', 'status']),
            ('idx_marketplace_items_category', 'marketplace_items', ['category']),
            ('idx_marketplace_items_author', 'marketplace_items', ['author_id']),
        ]:
            if not _index_exists(idx[1], idx[0]):
                op.create_index(idx[0], idx[1], idx[2], unique=False)

    if not _table_exists('saved_node_templates'):
        op.create_table(
            'saved_node_templates',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('step_type', sa.String(length=50), nullable=False),
            sa.Column('title', sa.String(length=255), nullable=False),
            sa.Column('description', sa.Text(), server_default=''),
            sa.Column('definition', sa.Text(), nullable=False),
            sa.Column('condition_expr', sa.Text(), server_default=''),
            sa.Column('is_enabled', sa.Boolean(), server_default='1'),
            sa.Column('max_retries', sa.Integer(), server_default='0'),
            sa.Column('retry_delay_seconds', sa.Integer(), server_default='0'),
            sa.Column('failure_hook_url', sa.String(length=500), server_default=''),
            sa.Column('source_marketplace_item_id', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.ForeignKeyConstraint(['source_marketplace_item_id'], ['marketplace_items.id']),
            sa.PrimaryKeyConstraint('id'),
        )

    if _table_exists('saved_node_templates'):
        for idx in [
            ('ix_saved_node_templates_id', 'saved_node_templates', ['id']),
            ('ix_saved_node_templates_user_id', 'saved_node_templates', ['user_id']),
            ('idx_saved_node_templates_user_step', 'saved_node_templates', ['user_id', 'step_type']),
        ]:
            if not _index_exists(idx[1], idx[0]):
                op.create_index(idx[0], idx[1], idx[2], unique=False)


def downgrade() -> None:
    op.drop_index('idx_saved_node_templates_user_step', table_name='saved_node_templates')
    op.drop_index('ix_saved_node_templates_user_id', table_name='saved_node_templates')
    op.drop_index('ix_saved_node_templates_id', table_name='saved_node_templates')
    op.drop_table('saved_node_templates')

    op.drop_index('idx_marketplace_items_author', table_name='marketplace_items')
    op.drop_index('idx_marketplace_items_category', table_name='marketplace_items')
    op.drop_index('idx_marketplace_items_type_status', table_name='marketplace_items')
    op.drop_index('ix_marketplace_items_name', table_name='marketplace_items')
    op.drop_index('ix_marketplace_items_id', table_name='marketplace_items')
    op.drop_table('marketplace_items')

"""add_services_and_categories_tables

Revision ID: a3671d8c9ed2
Revises: e2f3a4b5c6d7
Create Date: 2026-08-12 18:21:51.252956

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3671d8c9ed2'
down_revision: Union[str, None] = 'e2f3a4b5c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Categories table
    op.create_table(
        'categories',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(255), unique=True, nullable=False),
        sa.Column('key', sa.String(255), unique=True, nullable=False),
        sa.Column('icon', sa.String(10), server_default=''),
        sa.Column('description', sa.Text(), server_default=''),
        sa.Column('sort_order', sa.Integer(), server_default='0'),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(op.f('ix_categories_id'), 'categories', ['id'], unique=False)
    op.create_index(op.f('ix_categories_key'), 'categories', ['key'], unique=False)

    # Services table
    op.create_table(
        'services',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(255), unique=True, nullable=False),
        sa.Column('key', sa.String(255), unique=True, nullable=False),
        sa.Column('description', sa.Text(), server_default=''),
        sa.Column('icon', sa.String(10), server_default=''),
        sa.Column('category_id', sa.Integer(), sa.ForeignKey('categories.id'), nullable=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('support_group_id', sa.Integer(), sa.ForeignKey('groups.id'), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('sort_order', sa.Integer(), server_default='0'),
        sa.Column('custom_data', sa.JSON(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(op.f('ix_services_id'), 'services', ['id'], unique=False)
    op.create_index(op.f('ix_services_name'), 'services', ['name'], unique=False)
    op.create_index(op.f('ix_services_key'), 'services', ['key'], unique=False)

    # Add service_id to workflows (nullable FK)
    op.add_column(
        'workflows',
        sa.Column('service_id', sa.Integer(), sa.ForeignKey('services.id'), nullable=True)
    )
    op.create_index(op.f('ix_workflows_service_id'), 'workflows', ['service_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_workflows_service_id'), table_name='workflows')
    op.drop_column('workflows', 'service_id')

    op.drop_index(op.f('ix_services_id'), table_name='services')
    op.drop_index(op.f('ix_services_name'), table_name='services')
    op.drop_index(op.f('ix_services_key'), table_name='services')
    op.drop_table('services')

    op.drop_index(op.f('ix_categories_id'), table_name='categories')
    op.drop_index(op.f('ix_categories_key'), table_name='categories')
    op.drop_table('categories')

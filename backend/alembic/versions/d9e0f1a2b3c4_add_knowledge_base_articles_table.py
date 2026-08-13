"""add_knowledge_base_articles_table

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-08-12 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd9e0f1a2b3c4'
down_revision: Union[str, None] = 'c8d9e0f1a2b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'knowledge_base_articles',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('slug', sa.String(255), unique=True, nullable=False),
        sa.Column('content', sa.Text(), server_default=''),
        sa.Column('service_id', sa.Integer(), sa.ForeignKey('services.id'), nullable=True),
        sa.Column('is_published', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('sort_order', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(op.f('ix_knowledge_base_articles_id'), 'knowledge_base_articles', ['id'], unique=False)
    op.create_index(op.f('ix_knowledge_base_articles_title'), 'knowledge_base_articles', ['title'], unique=False)
    op.create_index(op.f('ix_knowledge_base_articles_slug'), 'knowledge_base_articles', ['slug'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_knowledge_base_articles_slug'), table_name='knowledge_base_articles')
    op.drop_index(op.f('ix_knowledge_base_articles_title'), table_name='knowledge_base_articles')
    op.drop_index(op.f('ix_knowledge_base_articles_id'), table_name='knowledge_base_articles')
    op.drop_table('knowledge_base_articles')

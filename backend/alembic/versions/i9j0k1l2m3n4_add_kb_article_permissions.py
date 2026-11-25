"""Add kb_article_permissions table for group-based visibility

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-08-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'i9j0k1l2m3n4'
down_revision: str = 'h8i9j0k1l2m3'
branch_labels: Union[tuple, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'kb_article_permissions')"
    ))
    if not result.scalar():
        op.create_table(
            'kb_article_permissions',
            sa.Column('article_id', sa.Integer(), nullable=False),
            sa.Column('group_id', sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint('article_id', 'group_id'),
            sa.ForeignKeyConstraint(['article_id'], ['knowledge_base_articles.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ondelete='CASCADE')
        )


def downgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'kb_article_permissions')"
    ))
    if result.scalar():
        op.drop_table('kb_article_permissions')

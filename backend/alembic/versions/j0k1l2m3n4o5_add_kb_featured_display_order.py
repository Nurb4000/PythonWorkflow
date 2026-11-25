"""Add is_featured and display_order to KB articles

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-08-19 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'j0k1l2m3n4o5'
down_revision: str = 'i9j0k1l2m3n4'
branch_labels: Union[tuple, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    conn = op.get_bind()

    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'knowledge_base_articles' AND column_name = 'is_featured')"
    ))
    if not result.scalar():
        op.add_column('knowledge_base_articles', sa.Column('is_featured', sa.Boolean(), server_default=sa.text('false'), nullable=False))

    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'knowledge_base_articles' AND column_name = 'display_order')"
    ))
    if not result.scalar():
        op.add_column('knowledge_base_articles', sa.Column('display_order', sa.Integer(), server_default=sa.text('0'), nullable=False))


def downgrade() -> None:
    conn = op.get_bind()

    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'knowledge_base_articles' AND column_name = 'display_order')"
    ))
    if result.scalar():
        op.drop_column('knowledge_base_articles', 'display_order')

    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'knowledge_base_articles' AND column_name = 'is_featured')"
    ))
    if result.scalar():
        op.drop_column('knowledge_base_articles', 'is_featured')

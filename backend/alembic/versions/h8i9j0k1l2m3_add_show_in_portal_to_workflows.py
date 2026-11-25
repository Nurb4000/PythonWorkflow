"""Add show_in_portal column to workflows

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-08-18 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'h8i9j0k1l2m3'
down_revision: Union[str, None] = 'g7h8i9j0k1l2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('workflows', sa.Column('show_in_portal', sa.Boolean(), nullable=True, server_default=sa.text('true')))
    # Set existing rows to True (show on portal)
    op.execute("UPDATE workflows SET show_in_portal = TRUE WHERE show_in_portal IS NULL")


def downgrade() -> None:
    op.drop_column('workflows', 'show_in_portal')

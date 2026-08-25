"""merge_roles_and_deprecation

Revision ID: f9cef82800d6
Revises: bc6fd2240266, 6af62d011f28
Create Date: 2026-08-25 23:31:49.781068

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f9cef82800d6'
down_revision: Union[str, None] = ('bc6fd2240266', '6af62d011f28')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

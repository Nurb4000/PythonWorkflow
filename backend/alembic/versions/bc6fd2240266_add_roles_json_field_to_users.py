"""add_roles_json_field_to_users

Revision ID: bc6fd2240266
Revises: d74a7f323ec9
Create Date: 2026-08-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'bc6fd2240266'
down_revision: Union[str, None] = 'd74a7f323ec9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('roles', sa.JSON(), server_default='[]'))


def downgrade() -> None:
    op.drop_column('users', 'roles')

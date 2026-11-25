"""add token_index to api_tokens for O(log n) API-token verification (findings #4)

Adds a deterministic HMAC-SHA256 index column so verify_api_token /
check_api_token_cmdb_permission can look a presented token up by value with a
single indexed read instead of bcrypt-verifying every active token (O(n)).

The column is nullable: tokens created before this migration have no plaintext
available to recompute the index (only the salted bcrypt hash is stored), so they
get NULL and must be re-issued. New tokens populate it on creation.

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
Create Date: 2026-11-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'n4o5p6q7r8s9'
down_revision: Union[str, None] = 'm3n4o5p6q7r8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'api_tokens',
        sa.Column('token_index', sa.String(length=64), nullable=True),
    )
    op.create_index(
        'ix_api_tokens_token_index', 'api_tokens', ['token_index'], unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_api_tokens_token_index', table_name='api_tokens')
    op.drop_column('api_tokens', 'token_index')

"""add refresh_tokens table for JWT refresh-token rotation

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-10-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = 'l2m3n4o5p6q7'
down_revision: Union[str, None] = 'k1l2m3n4o5p6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    insp = inspect(conn)
    return table_name in insp.get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    conn = op.get_bind()
    insp = inspect(conn)
    return any(idx['name'] == index_name for idx in insp.get_indexes(table_name))


def upgrade() -> None:
    if not _table_exists('refresh_tokens'):
        op.create_table(
            'refresh_tokens',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('token_index', sa.String(length=64), nullable=False),
            sa.Column('token_hash', sa.String(length=255), nullable=True),
            sa.Column('previous_token_index', sa.String(length=64), nullable=True),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('last_used_at', sa.DateTime(timezone=True)),
            sa.Column(
                'created_at',
                sa.DateTime(timezone=True),
                server_default=sa.text('CURRENT_TIMESTAMP'),
            ),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )

    if not _index_exists('refresh_tokens', 'uq_refresh_tokens_token_index'):
        op.create_index(
            'uq_refresh_tokens_token_index', 'refresh_tokens', ['token_index'], unique=True
        )

    if not _index_exists('refresh_tokens', 'ix_refresh_tokens_user_id'):
        op.create_index('ix_refresh_tokens_user_id', 'refresh_tokens', ['user_id'])

    # Link a rotated token to its predecessor so replay/leak detection can find an
    # active successor of a presented (now-retired) token.
    if not _index_exists('refresh_tokens', 'ix_refresh_tokens_previous_index'):
        op.create_index(
            'ix_refresh_tokens_previous_index', 'refresh_tokens', ['previous_token_index']
        )


def downgrade() -> None:
    op.drop_index('ix_refresh_tokens_previous_index', table_name='refresh_tokens')
    op.drop_index('ix_refresh_tokens_user_id', table_name='refresh_tokens')
    op.drop_index('uq_refresh_tokens_token_index', table_name='refresh_tokens')
    op.drop_table('refresh_tokens')

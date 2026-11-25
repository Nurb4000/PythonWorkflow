"""add token_revocations table for JWT logout/revocation

Revision ID: k1l2m3n4o5p6
Revises: a7b8c9d0e1f2
Create Date: 2026-10-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = 'k1l2m3n4o5p6'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
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
    if not _table_exists('token_revocations'):
        op.create_table(
            'token_revocations',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('jti', sa.String(length=64), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('reason', sa.String(length=255), nullable=True),
            sa.Column(
                'revoked_at',
                sa.DateTime(timezone=True),
                server_default=sa.text('CURRENT_TIMESTAMP'),
            ),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )

    if not _index_exists('token_revocations', 'uq_token_revocations_jti'):
        op.create_index(
            'uq_token_revocations_jti', 'token_revocations', ['jti'], unique=True
        )

    # NB: the primary key on `id` is auto-indexed by Postgres, so no explicit
    # index is created there. The unique constraint on `jti` (above) already
    # covers the revocation lookup; `user_id` is indexed for future
    # "list revoked tokens for a user" queries.
    if not _index_exists('token_revocations', 'ix_token_revocations_user_id'):
        op.create_index('ix_token_revocations_user_id', 'token_revocations', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_token_revocations_user_id', table_name='token_revocations')
    op.drop_index('uq_token_revocations_jti', table_name='token_revocations')
    op.drop_table('token_revocations')

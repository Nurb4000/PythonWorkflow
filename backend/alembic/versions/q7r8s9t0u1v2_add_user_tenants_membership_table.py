"""Add user_tenants membership table for multi-tenant users

A user may belong to more than one tenant. User.tenant_id remains the single
"default/primary" tenant (assigned at creation); this join table records the
*additional* tenants a user can switch into. Membership for scoping is
{user.tenant_id} UNION {tenant_ids in this table}, so existing users are
implicitly members of their default tenant with no backfill required.

Revision ID: q7r8s9t0u1v2
Revises: o5p6q7r8s9t0
Create Date: 2026-11-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'q7r8s9t0u1v2'
down_revision: Union[str, None] = 'o5p6q7r8s9t0'
branch_labels: Union[tuple, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'user_tenants')"
    ))
    if exists.scalar():
        return

    op.create_table(
        'user_tenants',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('is_admin', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint('user_id', 'tenant_id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    )
    op.create_index(
        'ix_user_tenants_tenant_id', 'user_tenants', ['tenant_id'], unique=False
    )


def downgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'user_tenants')"
    ))
    if not exists.scalar():
        return

    op.drop_index('ix_user_tenants_tenant_id', table_name='user_tenants')
    op.drop_table('user_tenants')

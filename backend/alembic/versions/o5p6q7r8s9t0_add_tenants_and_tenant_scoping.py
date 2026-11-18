"""add tenants table + tenant_id scoping for multi-tenancy (Feature-Plan §3.1 / gap 3.7)

Creates the `tenants` isolation-boundary table and adds a nullable `tenant_id`
foreign key to `users` and `groups`. Existing rows are backfilled into a seeded
"default" tenant so nothing breaks on upgrade. Groups are tenant-local, so
group->workflow permission grants cannot cross tenants and group-based access is
then automatically tenant-scoped (see app/services/tenant_scoping.py).

The column is nullable: the app always sets it for new rows, and existing rows are
backfilled here. NULL is interpreted by the scoping helper as "platform-wide"
(no isolation), which cannot happen after this migration because every existing
row is backfilled.

Raw DML uses `context.get_bind()` (the online-mode Connection) so it runs against
the same connection/transaction alembic uses for the surrounding DDL. The backfill
uses a subquery on the just-inserted default tenant, so no id round-trip is needed.

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2026-11-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import context
from alembic import op
import sqlalchemy as sa


revision: str = 'o5p6q7r8s9t0'
down_revision: Union[str, None] = 'n4o5p6q7r8s9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tenants',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('slug', sa.String(length=120), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_index('ix_tenants_slug', 'tenants', ['slug'], unique=True)
    op.create_index('ix_tenants_is_active', 'tenants', ['is_active'])

    conn = context.get_bind()
    # Seed the default tenant (id is auto-generated; backfill references it by slug).
    conn.execute(
        sa.text(
            "INSERT INTO tenants (name, slug, is_active) "
            "VALUES ('Default Tenant', 'default', true)"
        )
    )

    # Add nullable columns, then backfill existing rows via a subquery on the new
    # default tenant, then enforce referential integrity + NOT NULL.
    op.add_column('users', sa.Column('tenant_id', sa.Integer(), nullable=True))
    op.add_column('groups', sa.Column('tenant_id', sa.Integer(), nullable=True))

    conn.execute(sa.text(
        "UPDATE users SET tenant_id = "
        "(SELECT id FROM tenants WHERE slug = 'default') WHERE tenant_id IS NULL"
    ))
    conn.execute(sa.text(
        "UPDATE groups SET tenant_id = "
        "(SELECT id FROM tenants WHERE slug = 'default') WHERE tenant_id IS NULL"
    ))

    op.create_foreign_key(
        'fk_users_tenant', 'users', 'tenants', ['tenant_id'], ['id'],
    )
    op.create_foreign_key(
        'fk_groups_tenant', 'groups', 'tenants', ['tenant_id'], ['id'],
    )
    op.alter_column('users', 'tenant_id', nullable=False)
    op.alter_column('groups', 'tenant_id', nullable=False)


def downgrade() -> None:
    op.drop_constraint('fk_groups_tenant', 'groups', type_='foreignkey')
    op.drop_constraint('fk_users_tenant', 'users', type_='foreignkey')
    op.drop_column('groups', 'tenant_id')
    op.drop_column('users', 'tenant_id')
    op.drop_index('ix_tenants_is_active', 'tenants')
    op.drop_index('ix_tenants_slug', 'tenants')
    op.drop_table('tenants')

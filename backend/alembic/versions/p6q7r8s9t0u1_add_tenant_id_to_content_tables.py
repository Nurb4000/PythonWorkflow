"""add tenant_id to core content tables (Feature-Plan §3.1 / gap 3.7, part 2)

Extends tenant isolation from the auth layer (o5p6q7r8s9t0: tenants + users/groups)
to the primary tenant-owned content domain: the workflow execution graph and forms.
Each table gains a nullable `tenant_id` FK to `tenants`; existing rows are backfilled
into the seeded "default" tenant so single-tenant deployments keep working out of the
box. New rows always carry a tenant_id (set by the app), so isolation is enforced at
the SQL level by app/services/tenant_scoping.py.

Tables scoped (each independently by its own tenant_id):
  workflows, workflow_steps, workflow_runs, step_instances, tasks,
  forms, form_submissions, form_templates, form_uploads

Raw DML uses `context.get_bind()` (online-mode Connection) and backfills via a
subquery on the default tenant, so no id round-trip is needed.

Revision ID: p6q7r8s9t0u1
Revises: o5p6q7r8s9t0
Create Date: 2026-11-17 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import context
from alembic import op
import sqlalchemy as sa


revision: str = 'p6q7r8s9t0u1'
down_revision: Union[str, None] = 'o5p6q7r8s9t0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# table -> (column def). All use the same nullable FK; NOT NULL is enforced after
# backfill so a row can never silently escape scoping.
CONTENT_TABLES = [
    "workflows", "workflow_steps", "workflow_runs", "step_instances", "tasks",
    "forms", "form_submissions", "form_templates", "form_uploads",
]


def upgrade() -> None:
    conn = context.get_bind()

    # Ensure the default tenant exists before backfill (idempotent with o5p6...).
    default_id = conn.execute(
        sa.text("SELECT id FROM tenants WHERE slug = 'default'")
    ).scalar_one_or_none()
    if default_id is None:
        conn.execute(sa.text(
            "INSERT INTO tenants (name, slug, is_active) "
            "VALUES ('Default Tenant', 'default', true)"
        ))
        default_id = conn.execute(
            sa.text("SELECT id FROM tenants WHERE slug = 'default'")
        ).scalar_one()

    for table in CONTENT_TABLES:
        op.add_column(table, sa.Column('tenant_id', sa.Integer(), nullable=True))
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
        # Backfill existing rows to the default tenant, then enforce NOT NULL + FK.
        conn.execute(sa.text(
            f"UPDATE {table} SET tenant_id = "
            f"(SELECT id FROM tenants WHERE slug = 'default') WHERE tenant_id IS NULL"
        ))
        op.alter_column(table, "tenant_id", nullable=False)

    # Referential integrity last, once all rows satisfy it.
    for table in CONTENT_TABLES:
        op.create_foreign_key(
            f"fk_{table}_tenant", table, "tenants", ["tenant_id"], ["id"],
        )


def downgrade() -> None:
    # Reverse in the opposite order (FKs, then NOT NULL, then columns).
    for table in reversed(CONTENT_TABLES):
        op.drop_constraint(f"fk_{table}_tenant", table, type_='foreignkey')
    for table in reversed(CONTENT_TABLES):
        op.drop_index(f"ix_{table}_tenant_id", table)
        op.drop_column(table, "tenant_id")

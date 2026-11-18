"""
Tenant scoping helpers (Feature-Plan §3.1 / gap 3.7).

Central place that turns "the current user's tenant" into a WHERE clause applied to
any query, so tenant-owned data is isolated at the SQL level. This is the single
mechanism every endpoint uses to scope reads/writes; scoping it in one place keeps
isolation consistent and auditable.

Endpoint usage::

    from app.services.tenant_scoping import scope_current_tenant
    stmt = scope_current_tenant(db, select(Workflow).where(Workflow.is_active))

or with an explicit tenant id (admin cross-tenant reads, provisioning, tests)::

    from app.services.tenant_scoping import apply_tenant_scope
    stmt = apply_tenant_scope(select(Task), tenant_id=7)

Models that are NOT tenant-owned (users, groups, roles, permissions, audit logs,
api/refresh tokens, system_settings) are intentionally left unscoped — they are
platform-level. Tenant-owned content (workflows, runs, tasks, forms, CMDB, KB,
services, schedules, notifications, field definitions, reports, sql views,
marketplace items, email log) is scoped via the helpers above.
"""
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.auth import User
from app.models.tenancy import Tenant

# Slug/id of the tenant that existing rows are backfilled into. Kept in one place so
# migrations, bootstrap, and tests all agree.
DEFAULT_TENANT_SLUG = "default"
DEFAULT_TENANT_NAME = "Default Tenant"


def resolve_tenant_id(user: Optional[User]) -> Optional[int]:
    """Tenant a user's data should be scoped to (their ``tenant_id``).

    Returns ``None`` for anonymous/no-tenant callers, which callers interpret as
    "no scoping" (platform-wide). After the migration every real user has a
    non-null ``tenant_id``, so this is only None for anonymous access.
    """
    return user.tenant_id if user is not None else None


def apply_tenant_scope(
    query: Any,
    tenant_id: Optional[int],
    column: str = "tenant_id",
) -> Any:
    """Return ``query`` filtered to ``column == tenant_id``.

    If ``tenant_id`` is None the query is returned unchanged (platform-wide scope;
    the caller decides whether that is acceptable). The primary entity's column is
    used when resolvable (robust against joins); a single-table fallback uses the
    hardcoded column name, which is safe because it is a constant, not user input.
    """
    if tenant_id is None:
        return query

    entity = None
    if getattr(query, "column_descriptions", None):
        entity = query.column_descriptions[0].get("entity")

    if entity is not None and hasattr(entity, column):
        return query.where(getattr(entity, column) == tenant_id)

    # Single-table fallback: `column` is a hardcoded constant, so interpolation is safe.
    return query.where(text(f"{column} = {tenant_id}"))


def scope_current_tenant(db: Session, query: Any, user: Optional[User] = None) -> Any:
    """Convenience: scope ``query`` to ``user``'s tenant using the given session."""
    return apply_tenant_scope(query, resolve_tenant_id(user))


def ensure_default_tenant(db: Session) -> Tenant:
    """Return the seeded default tenant, creating it if missing.

    Used by bootstrap and tests so there is always a tenant to backfill/assign to.
    Idempotent.
    """
    from sqlalchemy import select

    tenant = db.execute(
        select(Tenant).where(Tenant.slug == DEFAULT_TENANT_SLUG)
    ).scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(name=DEFAULT_TENANT_NAME, slug=DEFAULT_TENANT_SLUG, is_active=True)
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
    return tenant

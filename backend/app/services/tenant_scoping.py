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

## Active tenant (multi-tenant switching)

A user may belong to several tenants (see ``app.models.auth.user_tenants``). The
*active* tenant for a request — the one the UI has currently selected — is carried in
the ``X-Tenant-Id`` request header and resolved by ``get_current_user`` (app.api.auth),
which validates membership and stores it in :data:`ACTIVE_TENANT_ID_CTX`.

``scope_current_tenant`` reads that contextvar first: when a request has selected a
tenant it scopes to that one; otherwise it falls back to ``user.tenant_id`` (the
user's default/primary tenant). This lets every existing call site stay unchanged
while supporting per-request tenant switching. The contextvar is set fresh on every
authenticated request (get_current_user always assigns it), so it never reads a stale
value from a previous request even when requests share a task.
"""
from contextvars import ContextVar
from typing import Any, List, Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import User, user_tenants
from app.models.tenancy import Tenant

# Slug/id of the tenant that existing rows are backfilled into. Kept in one place so
# migrations, bootstrap, and tests all agree.
DEFAULT_TENANT_SLUG = "default"
DEFAULT_TENANT_NAME = "Default Tenant"

# Active tenant for the current request. ``None`` (the default) means "no explicit
# selection" -> scope to the user's default tenant. Set by get_current_user (app.api.auth)
# on every authenticated request; read by scope_current_tenant. See the module docstring.
ACTIVE_TENANT_ID_CTX: ContextVar[Optional[int]] = ContextVar("active_tenant_id", default=None)


def resolve_tenant_id(user: Optional[User]) -> Optional[int]:
    """Default tenant a user's data should be scoped to (their ``tenant_id``).

    Returns ``None`` for anonymous/no-tenant callers, which callers interpret as
    "no scoping" (platform-wide). After the migration every real user has a
    non-null ``tenant_id``, so this is only None for anonymous access.
    """
    return user.tenant_id if user is not None else None


def get_active_tenant_id() -> Optional[int]:
    """Return the active tenant selected for the current request, or ``None``.

    ``None`` means no explicit selection was made (see the module docstring), in
    which case callers fall back to the user's default tenant.
    """
    return ACTIVE_TENANT_ID_CTX.get()


def set_active_tenant_id(value: Optional[int]) -> None:
    """Store the active tenant for the current request."""
    ACTIVE_TENANT_ID_CTX.set(value)


# Raw X-Tenant-Id header value for the current request, set by ActiveTenantMiddleware
# and resolved (parsed + membership-validated) by get_current_user into
# ACTIVE_TENANT_ID_CTX. Kept separate from the active-tenant contextvar so the raw
# request value survives even if validation fails, and so get_current_user needs no
# Request parameter (adding one to a FastAPI dependency silently breaks JSON body
# parsing for the whole route).
REQUESTED_TENANT_ID_CTX: ContextVar[Optional[str]] = ContextVar("requested_tenant_id", default=None)


def set_requested_tenant_id(value: Optional[str]) -> None:
    """Store the raw X-Tenant-Id header value for the current request."""
    REQUESTED_TENANT_ID_CTX.set(value)


def get_requested_tenant_id() -> Optional[str]:
    """Return the raw X-Tenant-Id header value, or ``None`` if none was sent."""
    return REQUESTED_TENANT_ID_CTX.get()


async def member_tenant_ids(db: AsyncSession, user: Optional[User]) -> set:
    """Return every tenant id ``user`` is allowed to operate in.

    Always includes the user's default ``tenant_id`` (implicit membership, so no
    backfill of existing users is needed) plus any additional tenants recorded in
    the ``user_tenants`` join table. Returns an empty set for anonymous callers.

    The join table is queried directly (rather than reading the ``user.tenants``
    relationship) so this works on an async session without triggering a lazy-load
    greenlet.
    """
    if user is None:
        return set()

    allowed = {user.tenant_id} if user.tenant_id is not None else set()
    result = await db.execute(
        select(user_tenants.c.tenant_id).where(user_tenants.c.user_id == user.id)
    )
    allowed.update(row[0] for row in result.all())
    return allowed


async def list_member_tenants(db: AsyncSession, user: Optional[User]) -> List[dict]:
    """Return the tenants ``user`` belongs to, as serialisable dicts.

    Used by the UI to populate the tenant switcher. Includes the user's default
    tenant (implicit membership) plus any additional tenants from ``user_tenants``.
    """
    if user is None:
        return []
    ids = await member_tenant_ids(db, user)
    stmt = select(Tenant)
    if ids:
        stmt = stmt.where(Tenant.id.in_(tuple(ids) if ids else (0,)))
    result = await db.execute(stmt)
    tenants = result.scalars().all()
    return [
        {"id": t.id, "name": t.name, "slug": t.slug, "is_active": t.is_active}
        for t in tenants
    ]


def scope_current_tenant(db: Session, query: Any, user: Optional[User] = None) -> Any:
    """Scope ``query`` to the effective tenant for this request.

    The effective tenant is the request's active tenant (``X-Tenant-Id`` header,
    resolved into :data:`ACTIVE_TENANT_ID_CTX` by the FastAPI dependency) when one
    has been selected, otherwise the user's default ``tenant_id``. This keeps every
    existing call site unchanged while supporting per-request tenant switching.
    """
    active = get_active_tenant_id()
    tenant_id = active if active is not None else resolve_tenant_id(user)
    return apply_tenant_scope(query, tenant_id)


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


async def resolve_creation_tenant_id(db: AsyncSession, user: Optional[User]) -> int:
    """Resolve the tenant id to assign to a newly created tenant-owned row.

    Uses the creating ``user``'s own tenant when present, otherwise falls back to the
    seeded default tenant (creating it if necessary). This is the write-side counterpart
    to :func:`resolve_tenant_id`: scoping helpers filter *reads* by tenant, while this
    guarantees every *new* row lands in a tenant so the NOT NULL ``tenant_id`` column
    enforced by the content migration is always satisfied.
    """
    if user is not None and user.tenant_id is not None:
        return user.tenant_id

    tenant = await db.execute(
        select(Tenant).where(Tenant.slug == DEFAULT_TENANT_SLUG)
    ).scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(name=DEFAULT_TENANT_NAME, slug=DEFAULT_TENANT_SLUG, is_active=True)
        db.add(tenant)
        await db.commit()
        await db.refresh(tenant)
    return tenant.id

"""
Tenant provisioning API (Feature-Plan §3.1 / gap 3.7).

Admin-only endpoints for managing ``Tenant`` (organization) records. A Tenant is the
multi-tenancy isolation boundary: every tenant-owned row carries a ``tenant_id`` that
is scoped to it at query time (see ``app/services/tenant_scoping.py``). These
endpoints are the control surface behind that model.

v1 scope: provisioning is admin-only. Content endpoints (workflows, runs, tasks,
forms, notifications, ...) restrict each caller to their own tenant via
``scope_current_tenant``; this console lets admins create and manage the tenant
registry itself.
"""
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_admin
from app.core.database import get_db
from app.models.auth import User, user_tenants
from app.models.tenancy import Tenant

router = APIRouter(tags=["tenants"])


def _slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    slug = re.sub(r'[^\w\s-]', '', text.lower()).strip().replace(' ', '-').replace('_', '-')
    return slug or 'tenant'


def _tenant_to_dict(t: Tenant) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "slug": t.slug,
        "is_active": t.is_active,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


class TenantCreate(BaseModel):
    """Body for POST /tenants."""

    name: str = Field(..., min_length=1, max_length=200, description="Display name for the tenant/organization")
    slug: Optional[str] = Field(
        None, max_length=120,
        description="URL-safe slug; auto-generated from `name` when omitted",
    )


class TenantUpdate(BaseModel):
    """Body for PUT /tenants/{tenant_id}."""

    name: Optional[str] = Field(None, min_length=1, max_length=200, description="New display name")
    is_active: Optional[bool] = Field(
        None,
        description="Deactivate (false) to lock the tenant out; activate (true) to restore.",
    )


@router.get("/", response_model=List[dict])
async def list_tenants(
    include_inactive: bool = Query(False, description="Include deactivated tenants"),
    limit: int = Query(100, ge=1, le=500),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all tenants (admin-only provisioning view)."""
    stmt = select(Tenant)
    if not include_inactive:
        stmt = stmt.where(Tenant.is_active == True)
    stmt = stmt.order_by(Tenant.name.asc()).limit(limit)
    result = await db.execute(stmt)
    tenants = result.scalars().all()
    return [_tenant_to_dict(t) for t in tenants]


@router.get("/{tenant_id}")
async def get_tenant(
    tenant_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get a single tenant by id (admin-only)."""
    stmt = select(Tenant).where(Tenant.id == tenant_id)
    result = await db.execute(stmt)
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return _tenant_to_dict(tenant)


@router.post("/")
async def create_tenant(
    data: TenantCreate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new tenant/organization (admin-only)."""
    slug = data.slug or _slugify(data.name)
    existing = await db.execute(select(Tenant).where(Tenant.slug == slug))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"A tenant with slug '{slug}' already exists")

    tenant = Tenant(name=data.name, slug=slug, is_active=True)
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return _tenant_to_dict(tenant)


@router.put("/{tenant_id}")
async def update_tenant(
    tenant_id: int,
    data: TenantUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update a tenant's name or active status (admin-only)."""
    stmt = select(Tenant).where(Tenant.id == tenant_id)
    result = await db.execute(stmt)
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if data.name is not None and data.name != tenant.name:
        new_slug = _slugify(data.name)
        if new_slug != tenant.slug:
            collision = await db.execute(
                select(Tenant).where(Tenant.slug == new_slug, Tenant.id != tenant_id)
            )
            if collision.scalar_one_or_none() is not None:
                raise HTTPException(status_code=409, detail=f"A tenant already uses slug '{new_slug}'")
        tenant.name = data.name
        tenant.slug = new_slug

    if data.is_active is not None:
        tenant.is_active = data.is_active

    await db.commit()
    await db.refresh(tenant)
    return _tenant_to_dict(tenant)


# --------------------------------------------------------------------------- #
# Tenant membership (multi-tenant switching)
#
# A user may belong to several tenants. These admin endpoints manage the
# ``user_tenants`` membership table on top of the provisioning CRUD above. Roles are
# applied globally across every tenant a user belongs to in this iteration; per-tenant
# roles are a planned follow-up.
# --------------------------------------------------------------------------- #
class AddMemberRequest(BaseModel):
    user_id: int = Field(..., description="Id of the user to add to this tenant")


def _member_to_dict(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "full_name": u.full_name,
        "role": u.role,
        "is_active": u.is_active,
    }


@router.get("/{tenant_id}/members")
async def list_tenant_members(
    tenant_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """List the users who are members of a tenant (admin-only)."""
    tenant = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    if tenant.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    result = await db.execute(
        select(User).where(User.id.in_(
            select(user_tenants.c.user_id).where(user_tenants.c.tenant_id == tenant_id)
        ))
    )
    users = result.scalars().all()
    # Always include the user's default tenant as a member even before it is recorded
    # in the join table, so the UI never drops a user's primary tenant.
    defaults = await db.execute(
        select(User).where(User.tenant_id == tenant_id)
    )
    default_users = defaults.scalars().all()
    seen = {u.id for u in users}
    for u in default_users:
        if u.id not in seen:
            users.append(u)
            seen.add(u.id)
    return [_member_to_dict(u) for u in sorted(users, key=lambda u: u.username)]


@router.post("/{tenant_id}/members")
async def add_tenant_member(
    tenant_id: int,
    data: AddMemberRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Add a user to a tenant (admin-only). Idempotent."""
    tenant = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    if tenant.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    user = await db.execute(select(User).where(User.id == data.user_id))
    target = user.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    existing = await db.execute(
        select(user_tenants).where(
            user_tenants.c.user_id == data.user_id,
            user_tenants.c.tenant_id == tenant_id,
        )
    )
    if existing.scalar_one_or_none() is None:
        await db.execute(user_tenants.insert().values(
            user_id=data.user_id, tenant_id=tenant_id, is_admin=False
        ))
        await db.commit()
    return {"user_id": data.user_id, "tenant_id": tenant_id, "added": True}


@router.delete("/{tenant_id}/members/{user_id}")
async def remove_tenant_member(
    tenant_id: int,
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Remove a user from a tenant (admin-only).

    Removing a user's *default* tenant from the join table is allowed; their
    ``users.tenant_id`` still scopes them to it, so this only drops any *additional*
    membership. Use it to revoke a user's access to a non-default tenant.
    """
    tenant = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    if tenant.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    result = await db.execute(
        select(user_tenants).where(
            user_tenants.c.user_id == user_id,
            user_tenants.c.tenant_id == tenant_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=409,
            detail="User is not a member of this tenant",
        )
    await db.execute(
        user_tenants.delete().where(
            user_tenants.c.user_id == user_id,
            user_tenants.c.tenant_id == tenant_id,
        )
    )
    await db.commit()
    return {"user_id": user_id, "tenant_id": tenant_id, "removed": True}

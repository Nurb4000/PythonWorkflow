"""In-app notification endpoints (Feature-Plan §2.3).

All endpoints are scoped to the authenticated user -- a user can only read, mark
read, or delete their own notifications. This mirrors the auth + pagination
conventions used by e.g. ``app/api/tasks.py``.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.services.tenant_scoping import scope_current_tenant
from app.models.auth import User
from app.models.schemas import Notification
from app.services.notification_service import unread_count

router = APIRouter()


@router.get("/notifications", response_model=dict)
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    unread: bool = Query(False, description="When true, only return unread notifications"),
    type: Optional[str] = Query(None, description="Filter by notification type"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List the current user's notifications (most recent first), paginated."""
    stmt = select(Notification).where(Notification.user_id == current_user.id)
    # Tenant isolation (§3.1): scope to the caller's tenant.
    stmt = scope_current_tenant(db, stmt, current_user)
    if unread:
        stmt = stmt.where(Notification.is_read.is_(False))
    if type:
        stmt = stmt.where(Notification.type == type)
    stmt = stmt.order_by(Notification.created_at.desc())

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()

    return {
        "notifications": [
            {
                "id": n.id,
                "title": n.title,
                "message": n.message,
                "type": n.type,
                "is_read": n.is_read,
                "related_entity_type": n.related_entity_type,
                "related_entity_id": n.related_entity_id,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/notifications/unread-count", response_model=dict)
async def unread_notification_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Unread count for the current user (drives the navbar badge)."""
    return {"unread": await unread_count(db, current_user.id)}


@router.post("/notifications/read-all", response_model=dict)
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark every unread notification owned by the current user as read."""
    items = (
        await db.execute(
            select(Notification).where(
                Notification.user_id == current_user.id,
                Notification.is_read.is_(False),
            )
        )
    ).scalars().all()
    for n in items:
        n.is_read = True
    await db.commit()
    return {"marked_read": len(items)}


@router.post("/notifications/{notification_id}/read", response_model=dict)
async def mark_notification_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a single owned notification as read (403 if it belongs to someone else)."""
    n = (
        await db.execute(select(Notification).where(Notification.id == notification_id))
    ).scalar_one_or_none()
    if n is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    if n.user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not permitted to modify this notification"
        )
    n.is_read = True
    await db.commit()
    return {"id": n.id, "is_read": True}


@router.delete("/notifications/{notification_id}", response_model=dict)
async def delete_notification(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a single owned notification (403 if it belongs to someone else)."""
    n = (
        await db.execute(select(Notification).where(Notification.id == notification_id))
    ).scalar_one_or_none()
    if n is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    if n.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not permitted to delete this notification")
    await db.delete(n)
    await db.commit()
    return {"id": n.id, "deleted": True}

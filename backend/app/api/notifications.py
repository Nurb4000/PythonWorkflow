"""In-app notification endpoints (Feature-Plan §2.3).

All endpoints are scoped to the authenticated user -- a user can only read, mark
read, or delete their own notifications. This mirrors the auth + pagination
conventions used by e.g. ``app/api/tasks.py``.

G4 also exposes channel *configuration* here: listing external-channel status,
updating channel config + routing (admin), and testing a channel. Config is
persisted in system_settings (encrypted secrets included) and applied to the
runtime settings object immediately, mirroring the email-settings endpoints in
``app/api/system_settings.py``.
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.services.tenant_scoping import scope_current_tenant
from app.models.auth import User
from app.models.schemas import Notification
from app.services.notification_channels import (
    ChannelType,
    NotificationTarget,
    notification_dispatcher,
)
from app.services.notification_service import (
    ROUTING_SETTING_KEY,
    unread_count,
)
from app.api.system_settings import get_setting, set_setting

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


# ------------------------------------------------------------------
# G4: external notification channel configuration
# ------------------------------------------------------------------


class ChannelConfigUpdate(BaseModel):
    """Payload for updating external notification channel config + routing."""

    slack_webhook_url: Optional[str] = None
    webhook_url: Optional[str] = None  # generic outgoing webhook endpoint
    webhook_secret: Optional[str] = None  # signing secret; omit to leave unchanged
    routing: Optional[dict[str, list[str]]] = None


class ChannelStatus(BaseModel):
    type: str
    name: str
    configured: bool


@router.get("/notifications/channels", response_model=dict)
async def list_channel_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """External-channel status + current routing (read-only, no secrets)."""
    channels = notification_dispatcher._channels
    status = [
        ChannelStatus(
            type=ch.type.value,
            name=ch.name,
            configured=await ch.is_configured(),
        )
        for ch in channels.values()
    ]
    routing = await get_setting(db, ROUTING_SETTING_KEY, "")
    return {"channels": [c.model_dump() for c in status], "routing": json.loads(routing) if routing else {}}


@router.put("/notifications/channels", response_model=dict)
async def update_channel_config(
    payload: ChannelConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update external channel config + routing (admin only).

    Applies to the runtime settings object immediately AND persists to
    system_settings so overrides survive restarts (re-applied at startup by
    notification_service.load_channel_overrides / apply_routing).
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    from app.core.config import settings

    if payload.slack_webhook_url is not None:
        settings.slack_webhook_url = payload.slack_webhook_url.strip()
        await set_setting(db, "slack_webhook_url", settings.slack_webhook_url)

    if payload.webhook_url is not None:
        settings.webhook_url = payload.webhook_url.strip()
        await set_setting(db, "webhook_url", settings.webhook_url)

    if payload.webhook_secret is not None:
        settings.webhook_secret = payload.webhook_secret
        # Encrypted at rest automatically (webhook_secret is in SECRET_SETTING_KEYS).
        await set_setting(db, "webhook_secret", payload.webhook_secret)

    if payload.routing is not None:
        # Validate shape before persisting.
        if not all(
            isinstance(k, str) and isinstance(v, list) for k, v in payload.routing.items()
        ):
            raise HTTPException(status_code=400, detail="routing must be {type: [channel, ...]}")
        await set_setting(db, ROUTING_SETTING_KEY, json.dumps(payload.routing))
        notification_dispatcher.routing.clear()
        notification_dispatcher.routing.update(payload.routing)

    await db.commit()
    return {"message": "Notification channel settings updated"}


@router.post("/notifications/channels/test", response_model=dict)
async def test_channel(
    channel: str = Query(..., description="email | slack | webhook"),
    current_user: User = Depends(get_current_user),
):
    """Send a sample notification through one channel and return diagnostics.

    Always responds 200 with the per-recipient results so the UI can show where
    delivery failed (mirrors POST /settings/test-email).
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        ctype = ChannelType(channel)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown channel '{channel}'")

    ch = notification_dispatcher.get(ctype)
    if ch is None:
        raise HTTPException(status_code=404, detail=f"Channel '{channel}' not registered")

    target = NotificationTarget(
        type="workflow_failed",
        title="Instant Workflow — test notification",
        message="This confirms the external notification channel is configured correctly.",
        recipients=[current_user.email] if getattr(current_user, "email", None) else [],
        context={"test": True},
    )
    results = await ch.send(target)
    return {"channel": channel, "results": [r.model_dump() for r in results]}

"""Admin API for the persistent webhook execution log (M4).

All endpoints are admin-only: log rows can contain internal endpoints, IP
addresses and redacted payloads, so they are not exposed to regular users.
Payloads are returned only by the detail endpoint to keep list queries small.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_admin
from app.core.database import get_db
from app.models.auth import User
from app.models.webhook_log import WebhookLog
from app.services import webhook_log_service as webhook_logs
from app.services.tenant_scoping import get_active_tenant_id, resolve_tenant_id

router = APIRouter()


def _effective_tenant_id(current_user: User) -> Optional[int]:
    """Active tenant for this request, falling back to the user's default tenant."""
    active = get_active_tenant_id()
    return active if active is not None else resolve_tenant_id(current_user)


def _scoped(stmt, tenant_id: Optional[int]):
    """Restrict logs to the caller's tenant plus platform-level (null-tenant) rows."""
    if tenant_id is None:
        return stmt
    return stmt.where(
        or_(WebhookLog.tenant_id == tenant_id, WebhookLog.tenant_id.is_(None))
    )


@router.get("/webhook-logs")
async def list_webhook_logs(
    direction: Optional[str] = Query(None, description="incoming | outgoing"),
    event_type: Optional[str] = None,
    status: Optional[str] = None,
    success: Optional[bool] = None,
    workflow_id: Optional[int] = None,
    run_id: Optional[int] = None,
    idempotency_key: Optional[str] = None,
    q: Optional[str] = Query(None, description="Search endpoint, detail or idempotency key"),
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """List webhook events, newest first, with optional filters (admin only)."""
    stmt = _scoped(select(WebhookLog), _effective_tenant_id(current_user))
    if direction:
        stmt = stmt.where(WebhookLog.direction == direction)
    if event_type:
        stmt = stmt.where(WebhookLog.event_type == event_type)
    if status:
        stmt = stmt.where(WebhookLog.status == status)
    if success is not None:
        stmt = stmt.where(WebhookLog.success.is_(success))
    if workflow_id is not None:
        stmt = stmt.where(WebhookLog.workflow_id == workflow_id)
    if run_id is not None:
        stmt = stmt.where(WebhookLog.run_id == run_id)
    if idempotency_key:
        stmt = stmt.where(WebhookLog.idempotency_key == idempotency_key)
    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                WebhookLog.endpoint.ilike(term),
                WebhookLog.detail.ilike(term),
                WebhookLog.idempotency_key.ilike(term),
            )
        )
    if since:
        stmt = stmt.where(WebhookLog.created_at >= since)
    if until:
        stmt = stmt.where(WebhookLog.created_at <= until)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        await db.execute(
            stmt.order_by(WebhookLog.created_at.desc(), WebhookLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return {
        "items": [webhook_logs.serialize_log(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/webhook-logs/stats")
async def webhook_log_stats(
    hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Summary counters for the dashboard over the last ``hours``."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    scoped = _scoped(
        select(WebhookLog).where(WebhookLog.created_at >= cutoff),
        _effective_tenant_id(current_user),
    ).subquery()
    grouped = (
        await db.execute(
            select(scoped.c.direction, scoped.c.success, func.count())
            .group_by(scoped.c.direction, scoped.c.success)
        )
    ).all()
    stats = {
        "window_hours": hours,
        "total": 0,
        "incoming": 0,
        "outgoing": 0,
        "success": 0,
        "failed": 0,
    }
    for direction, success, count in grouped:
        stats["total"] += count
        stats[direction] = stats.get(direction, 0) + count
        stats["success" if success else "failed"] += count

    stats["retries"] = (
        await db.execute(
            select(func.count())
            .select_from(scoped)
            .where(scoped.c.will_retry.is_(True))
        )
    ).scalar_one()
    avg_duration = (
        await db.execute(
            select(func.avg(scoped.c.duration_ms)).where(
                scoped.c.duration_ms.is_not(None)
            )
        )
    ).scalar()
    stats["avg_duration_ms"] = round(avg_duration) if avg_duration is not None else None
    return stats


@router.get("/webhook-logs/{log_id}")
async def get_webhook_log(
    log_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Full detail for one webhook event, including its redacted payload."""
    stmt = _scoped(select(WebhookLog), _effective_tenant_id(current_user)).where(
        WebhookLog.id == log_id
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Webhook log not found")
    return webhook_logs.serialize_log(row, include_payload=True)


@router.delete("/webhook-logs")
async def cleanup_webhook_logs(
    older_than_days: int = Query(30, ge=0, le=3650),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Delete log rows older than ``older_than_days`` (admin only)."""
    deleted = await webhook_logs.prune_webhook_logs(
        older_than_days, tenant_id=_effective_tenant_id(current_user)
    )
    return {"deleted": deleted, "older_than_days": older_than_days}

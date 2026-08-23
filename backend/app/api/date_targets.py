"""
Date target tracking API — INCIDENT_CHANGE_PLAN Phase 0.3

Provides CRUD for date-based targets (calendar deadlines) attached to
workflow runs, steps, or tasks. Used by change management and any flow
that needs absolute deadline tracking rather than relative SLA/OLA hours.
"""
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.models.auth import User
from app.api.auth import get_current_user, get_current_admin
from app.models.date_targets import DateTarget

router = APIRouter()


def _target_to_dict(t: DateTarget) -> dict:
    return {
        "id": t.id,
        "workflow_run_id": t.workflow_run_id,
        "step_id": t.step_id,
        "task_id": t.task_id,
        "target_key": t.target_key,
        "target_datetime": t.target_datetime.isoformat() if t.target_datetime else None,
        "status": t.status,
        "custom_data": t.custom_data or {},
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


@router.get("")
async def list_date_targets(
    run_id: Optional[int] = Query(None, description="Filter by workflow run ID"),
    status: Optional[str] = Query(None, description="Filter by status (pending/met/breached)"),
    target_key: Optional[str] = Query(None, description="Filter by target key"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List date targets with optional filters."""
    stmt = select(DateTarget)

    if run_id is not None:
        stmt = stmt.where(DateTarget.workflow_run_id == run_id)
    if status:
        stmt = stmt.where(DateTarget.status == status)
    if target_key:
        stmt = stmt.where(DateTarget.target_key == target_key)

    stmt = stmt.order_by(DateTarget.target_datetime.asc())
    result = await db.execute(stmt)
    targets = result.scalars().all()

    return [_target_to_dict(t) for t in targets]


@router.get("/stats")
async def get_date_target_stats(
    days: int = Query(30, ge=1, le=365, description="Lookback window in days"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return compliance stats for date targets over the given period."""
    from datetime import timezone as tz, timedelta

    cutoff = datetime.now(tz.utc) - timedelta(days=days)

    stmt = select(
        func.count(DateTarget.id),
        func.sum(func.case((DateTarget.status == "met", 1), else_=0)),
        func.sum(func.case((DateTarget.status == "breached", 1), else_=0)),
        func.sum(func.case((DateTarget.status == "pending", 1), else_=0)),
    ).where(
        DateTarget.created_at >= cutoff
    )
    result = await db.execute(stmt)
    row = result.one()

    total = row[0] or 0
    met = row[1] or 0
    breached = row[2] or 0
    pending = row[3] or 0
    evaluated = met + breached
    compliance_pct = round((met / evaluated * 100), 1) if evaluated > 0 else None

    return {
        "total": total,
        "met": met,
        "breached": breached,
        "pending": pending,
        "compliance_pct": compliance_pct,
        "period_days": days,
    }


@router.post("")
async def create_date_target(
    target_data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Create a new date target. Admin only."""
    required = ["workflow_run_id", "target_key", "target_datetime"]
    for field in required:
        if field not in target_data:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    try:
        target_dt = datetime.fromisoformat(target_data["target_datetime"].replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid target_datetime format. Use ISO 8601.")

    target = DateTarget(
        workflow_run_id=target_data["workflow_run_id"],
        step_id=target_data.get("step_id"),
        task_id=target_data.get("task_id"),
        target_key=target_data["target_key"],
        target_datetime=target_dt,
        status="pending",
        custom_data=target_data.get("custom_data", {}),
    )
    db.add(target)
    await db.flush()
    await db.commit()

    return _target_to_dict(target)


@router.patch("/{target_id}")
async def update_date_target(
    target_id: int,
    target_data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Update a date target (e.g., mark as met). Admin only."""
    stmt = select(DateTarget).where(DateTarget.id == target_id)
    result = await db.execute(stmt)
    target = result.scalar_one_or_none()

    if not target:
        raise HTTPException(status_code=404, detail="Date target not found")

    updatable = {"status", "target_datetime", "custom_data"}
    for key, value in target_data.items():
        if key in updatable:
            if key == "target_datetime" and value is not None:
                try:
                    value = datetime.fromisoformat(value.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    raise HTTPException(status_code=400, detail="Invalid target_datetime format.")
            setattr(target, key, value)

    await db.commit()
    return _target_to_dict(target)


@router.delete("/{target_id}")
async def delete_date_target(
    target_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Deactivate a date target. Admin only."""
    stmt = select(DateTarget).where(DateTarget.id == target_id)
    result = await db.execute(stmt)
    target = result.scalar_one_or_none()

    if not target:
        raise HTTPException(status_code=404, detail="Date target not found")

    target.is_active = False
    await db.commit()
    return {"detail": "Date target deactivated"}

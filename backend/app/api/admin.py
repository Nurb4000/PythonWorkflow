"""
Admin API endpoints for monitoring and reporting
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import List, Optional
from datetime import datetime, timedelta

from app.core.database import get_db
from app.models.schemas import Workflow, WorkflowRun, StepInstance, Schedule
from app.schemas.workflow import RunStatsResponse, AuditLogEntry

router = APIRouter()


@router.get("/stats", response_model=RunStatsResponse)
async def get_run_stats(
    workflow_id: Optional[int] = None,
    days: int = 30,
    db: AsyncSession = Depends(get_db)
):
    """Get workflow execution statistics"""
    now = datetime.utcnow()
    since = now - timedelta(days=days)
    
    stmt = select(WorkflowRun).where(WorkflowRun.created_at >= since)
    
    if workflow_id:
        stmt = stmt.where(WorkflowRun.workflow_id == workflow_id)
    
    result = await db.execute(stmt)
    runs = result.scalars().all()
    
    total = len(runs)
    completed = sum(1 for r in runs if r.status == "completed")
    failed = sum(1 for r in runs if r.status == "failed")
    
    # Calculate average duration
    durations = []
    for run in runs:
        if run.started_at and run.completed_at:
            duration = (run.completed_at - run.started_at).total_seconds()
            durations.append(duration)
    
    avg_duration = sum(durations) / len(durations) if durations else 0.0
    
    last_run = max([r.created_at for r in runs], default=None)
    
    return RunStatsResponse(
        total_runs=total,
        completed_runs=completed,
        failed_runs=failed,
        average_duration_seconds=avg_duration,
        last_run_at=last_run
    )


@router.get("/runs", response_model=List[dict])
async def list_all_runs(
    status: Optional[str] = None,
    workflow_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """List all workflow runs with filters"""
    stmt = select(WorkflowRun)
    
    if status:
        stmt = stmt.where(WorkflowRun.status == status)
    if workflow_id:
        stmt = stmt.where(WorkflowRun.workflow_id == workflow_id)
    
    stmt = stmt.order_by(WorkflowRun.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    runs = result.scalars().all()
    
    return [
        {
            "id": run.id,
            "workflow_id": run.workflow_id,
            "status": run.status,
            "triggered_by": run.triggered_by,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "created_at": run.created_at,
            "error_message": run.error_message
        }
        for run in runs
    ]


@router.get("/workflows/{workflow_id}/audit-log")
async def get_audit_log(
    workflow_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get detailed audit log for a workflow"""
    # Get all runs for this workflow
    stmt = (
        select(WorkflowRun)
        .where(WorkflowRun.workflow_id == workflow_id)
        .order_by(WorkflowRun.created_at.desc())
    )
    result = await db.execute(stmt)
    runs = result.scalars().all()
    
    audit_log = []
    for run in runs:
        audit_log.append({
            "timestamp": run.created_at,
            "action": f"workflow_run_{run.status}",
            "user": run.triggered_by,
            "details": {
                "run_id": run.id,
                "started_at": run.started_at,
                "completed_at": run.completed_at,
                "error": run.error_message
            }
        })
    
    return audit_log


@router.get("/schedules")
async def list_schedules(db: AsyncSession = Depends(get_db)):
    """List all schedules"""
    stmt = select(Schedule).order_by(Schedule.created_at.desc())
    result = await db.execute(stmt)
    schedules = result.scalars().all()
    
    return [
        {
            "id": s.id,
            "workflow_id": s.workflow_id,
            "cron_expression": s.cron_expression,
            "is_enabled": s.is_enabled,
            "last_run_at": s.last_run_at,
            "next_run_at": s.next_run_at
        }
        for s in schedules
    ]


@router.post("/schedules")
async def create_schedule(schedule_data: dict, db: AsyncSession = Depends(get_db)):
    """Create a new schedule"""
    schedule = Schedule(
        workflow_id=schedule_data["workflow_id"],
        cron_expression=schedule_data["cron_expression"],
        is_enabled=schedule_data.get("is_enabled", True)
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    
    return {
        "id": schedule.id,
        "workflow_id": schedule.workflow_id,
        "cron_expression": schedule.cron_expression,
        "is_enabled": schedule.is_enabled,
        "last_run_at": schedule.last_run_at,
        "next_run_at": schedule.next_run_at
    }


@router.put("/schedules/{schedule_id}")
async def update_schedule(schedule_id: int, schedule_data: dict, db: AsyncSession = Depends(get_db)):
    """Update a schedule"""
    stmt = select(Schedule).where(Schedule.id == schedule_id)
    result = await db.execute(stmt)
    schedule = result.scalar_one_or_none()
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    if "cron_expression" in schedule_data:
        schedule.cron_expression = schedule_data["cron_expression"]
    if "is_enabled" in schedule_data:
        schedule.is_enabled = schedule_data["is_enabled"]
    
    await db.commit()
    await db.refresh(schedule)
    
    return {
        "id": schedule.id,
        "workflow_id": schedule.workflow_id,
        "cron_expression": schedule.cron_expression,
        "is_enabled": schedule.is_enabled,
        "last_run_at": schedule.last_run_at,
        "next_run_at": schedule.next_run_at
    }


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(schedule_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a schedule"""
    stmt = select(Schedule).where(Schedule.id == schedule_id)
    result = await db.execute(stmt)
    schedule = result.scalar_one_or_none()
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    await db.delete(schedule)
    await db.commit()
    
    return {"message": "Schedule deleted successfully"}

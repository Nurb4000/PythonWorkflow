"""
Admin API endpoints for monitoring and reporting
"""
import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from typing import List, Optional
from datetime import datetime, timedelta

from app.core.database import get_db
from app.models.auth import User
from app.models.schemas import Workflow, WorkflowRun, StepInstance, Schedule
from app.schemas.workflow import RunStatsResponse, AuditLogEntry
from app.api.auth import get_current_admin
from app.services.scheduler import scheduler_service

router = APIRouter()


def validate_cron_expression(cron_expr: str) -> bool:
    """Validate a cron expression (5-part format)"""
    parts = cron_expr.split()
    if len(parts) != 5:
        return False
    
    # Basic validation for each field
    minute, hour, day, month, day_of_week = parts
    
    # Minute: 0-59
    if not re.match(r'^(\*|[0-5]?[0-9])(-[0-5]?[0-9])?$', minute):
        return False
    
    # Hour: 0-23
    if not re.match(r'^(\*|([01]?[0-9]|2[0-3]))(-([01]?[0-9]|2[0-3]))?$', hour):
        return False
    
    # Day: 1-31
    if not re.match(r'^(\*|([1-9]|[12]\d|3[01]))(-([1-9]|[12]\d|3[01]))?$', day):
        return False
    
    # Month: 1-12
    if not re.match(r'^(\*|([1-9]|1[012]))(-([1-9]|1[012]))?$', month):
        return False
    
    # Day of week: 0-6 (Sun-Sat)
    if not re.match(r'^(\*|[0-6])(-[0-6])?$', day_of_week):
        return False
    
    return True


@router.get("/stats", response_model=RunStatsResponse)
async def get_run_stats(
    workflow_id: Optional[int] = None,
    days: int = 30,
    current_user: User = Depends(get_current_admin),
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
    q: Optional[str] = None,
    limit: int = 500,
    offset: int = 0,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all workflow runs with workflow name and step/node summary"""
    stmt = (
        select(WorkflowRun, Workflow.name.label("workflow_name"))
        .join(Workflow, Workflow.id == WorkflowRun.workflow_id)
    )
    
    if status:
        stmt = stmt.where(WorkflowRun.status == status)
    if workflow_id:
        stmt = stmt.where(WorkflowRun.workflow_id == workflow_id)
    if q:
        q = q.strip()
        if q:
            try:
                run_id = int(q)
                stmt = stmt.where(
                    or_(
                        WorkflowRun.id == run_id,
                        Workflow.name.contains(q),
                        WorkflowRun.triggered_by.contains(q),
                        WorkflowRun.status.contains(q)
                    )
                )
            except ValueError:
                stmt = stmt.where(
                    or_(
                        Workflow.name.contains(q),
                        WorkflowRun.triggered_by.contains(q),
                        WorkflowRun.status.contains(q)
                    )
                )
    
    stmt = stmt.order_by(WorkflowRun.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    rows = result.all()
    
    # Aggregate step instance statuses per run (the "nodes")
    run_ids = [row.WorkflowRun.id for row in rows]
    step_summary: dict = {}
    if run_ids:
        agg_stmt = (
            select(StepInstance.workflow_run_id, StepInstance.status, func.count(StepInstance.id))
            .where(StepInstance.workflow_run_id.in_(run_ids))
            .group_by(StepInstance.workflow_run_id, StepInstance.status)
        )
        agg_result = await db.execute(agg_stmt)
        for run_id, status_name, count in agg_result.all():
            step_summary.setdefault(run_id, {})[status_name] = count
    
    return [
        {
            "id": run.id,
            "workflow_id": run.workflow_id,
            "workflow_name": workflow_name,
            "status": run.status,
            "triggered_by": run.triggered_by,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "created_at": run.created_at,
            "error_message": run.error_message,
            "steps_total": sum((step_summary.get(run.id, {}) or {}).values()),
            "steps_completed": (step_summary.get(run.id, {}) or {}).get("completed", 0),
            "steps_failed": (step_summary.get(run.id, {}) or {}).get("failed", 0),
            "steps_running": (step_summary.get(run.id, {}) or {}).get("running", 0),
            "steps_pending": (step_summary.get(run.id, {}) or {}).get("pending", 0),
            "steps_skipped": (step_summary.get(run.id, {}) or {}).get("skipped", 0)
        }
        for run, workflow_name in rows
    ]


@router.get("/workflows/{workflow_id}/audit-log")
async def get_audit_log(
    workflow_id: int,
    current_user: User = Depends(get_current_admin),
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
async def list_schedules(current_user: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
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
async def create_schedule(
    schedule_data: dict,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a new schedule"""
    
    # Validate cron expression
    if not validate_cron_expression(schedule_data["cron_expression"]):
        raise HTTPException(
            status_code=400, 
            detail="Invalid cron expression. Use 5-part format: minute hour day month day_of_week"
        )
    
    # Verify workflow exists
    stmt = select(Workflow).where(Workflow.id == schedule_data["workflow_id"])
    result = await db.execute(stmt)
    workflow = result.scalar_one_or_none()
    
    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow {schedule_data['workflow_id']} not found")
    
    schedule = Schedule(
        workflow_id=schedule_data["workflow_id"],
        cron_expression=schedule_data["cron_expression"],
        is_enabled=schedule_data.get("is_enabled", True)
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    
    # Add to scheduler if enabled
    if schedule.is_enabled:
        scheduler_service.add_schedule(schedule)
    
    return {
        "id": schedule.id,
        "workflow_id": schedule.workflow_id,
        "cron_expression": schedule.cron_expression,
        "is_enabled": schedule.is_enabled,
        "last_run_at": schedule.last_run_at,
        "next_run_at": schedule.next_run_at
    }


@router.put("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: int,
    schedule_data: dict,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update a schedule"""
    stmt = select(Schedule).where(Schedule.id == schedule_id)
    result = await db.execute(stmt)
    schedule = result.scalar_one_or_none()
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    # Validate cron expression if provided
    if "cron_expression" in schedule_data:
        if not validate_cron_expression(schedule_data["cron_expression"]):
            raise HTTPException(
                status_code=400, 
                detail="Invalid cron expression. Use 5-part format: minute hour day month day_of_week"
            )
        schedule.cron_expression = schedule_data["cron_expression"]
    
    if "is_enabled" in schedule_data:
        schedule.is_enabled = schedule_data["is_enabled"]
    
    await db.commit()
    await db.refresh(schedule)
    
    # Update scheduler
    if schedule.is_enabled:
        scheduler_service.update_schedule(schedule)
    else:
        scheduler_service.remove_schedule(schedule_id)
    
    return {
        "id": schedule.id,
        "workflow_id": schedule.workflow_id,
        "cron_expression": schedule.cron_expression,
        "is_enabled": schedule.is_enabled,
        "last_run_at": schedule.last_run_at,
        "next_run_at": schedule.next_run_at
    }


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a schedule"""
    stmt = select(Schedule).where(Schedule.id == schedule_id)
    result = await db.execute(stmt)
    schedule = result.scalar_one_or_none()
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    # Remove from scheduler
    scheduler_service.remove_schedule(schedule_id)
    
    await db.delete(schedule)
    await db.commit()
    
    return {"message": "Schedule deleted successfully"}


@router.post("/schedules/{schedule_id}/test")
async def test_schedule(
    schedule_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Test a schedule by immediately triggering the workflow"""
    stmt = select(Schedule).where(Schedule.id == schedule_id)
    result = await db.execute(stmt)
    schedule = result.scalar_one_or_none()
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    try:
        # Trigger the workflow immediately
        run = await scheduler_service.trigger_external_api(
            schedule.workflow_id,
            {"test": True, "scheduled_by": "manual_test"}
        )
        
        return {
            "success": True,
            "run_id": run.id,
            "message": "Schedule test triggered successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Test trigger failed: {str(e)}")

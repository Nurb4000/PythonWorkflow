"""
Admin API endpoints for monitoring and reporting
"""
import asyncio
import io
import logging
import re
import subprocess
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from typing import List, Optional
from datetime import datetime, timedelta

from app.core.database import get_db
from app.models.auth import User
from app.models.forms import FormUpload
from app.models.schemas import Workflow, WorkflowRun, StepInstance, Schedule
from app.schemas.workflow import RunStatsResponse, AuditLogEntry
from app.api.auth import get_current_admin
from app.services.scheduler import scheduler_service

router = APIRouter()


# In-memory log buffer for recent entries (thread-safe)
import threading
_log_buffer: List[str] = []
_log_lock = threading.Lock()
_MAX_LOG_ENTRIES = 10000


class LogCaptureHandler(logging.Handler):
    """Captures log records and stores them in memory."""
    def emit(self, record):
        msg = self.format(record)
        with _log_lock:
            _log_buffer.append(msg)
            if len(_log_buffer) > _MAX_LOG_ENTRIES:
                _log_buffer[:] = _log_buffer[-_MAX_LOG_ENTRIES:]


# Attach to root logger
_capture_handler = LogCaptureHandler()
_capture_handler.setLevel(logging.DEBUG)
_capture_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
logging.getLogger().addHandler(_capture_handler)


@router.get("/logs")
async def get_system_logs(
    level: Optional[str] = None,
    search: Optional[str] = None,
    lines: int = 500,
    source: str = "app",
    current_user: User = Depends(get_current_admin),
):
    """Get system logs. source='app' for in-memory Python logs, source='docker' for container logs."""
    if source == "docker":
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: subprocess.run(
                    ["docker", "logs", "--tail", str(lines * 2), "pythonworkflow-backend"],
                    capture_output=True, text=True, timeout=10
                )
            )
            log_lines = result.stderr.splitlines() if result.stderr else []
        except Exception:
            log_lines = list(_log_buffer)
    else:
        log_lines = list(_log_buffer)

    # Filter by level
    if level:
        level_upper = level.upper()
        log_lines = [l for l in log_lines if f"[{level_upper}]" in l]

    # Filter by search term
    if search:
        search_lower = search.lower()
        log_lines = [l for l in log_lines if search_lower in l.lower()]

    # Return last N lines
    return {
        "logs": log_lines[-lines:],
        "total_count": len(log_lines),
        "source": source,
    }


@router.get("/logs/export")
async def export_system_logs(
    level: Optional[str] = None,
    search: Optional[str] = None,
    lines: int = 5000,
    current_user: User = Depends(get_current_admin),
):
    """Export system logs as a downloadable text file."""
    log_lines = list(_log_buffer)

    if level:
        level_upper = level.upper()
        log_lines = [l for l in log_lines if f"[{level_upper}]" in l]

    if search:
        search_lower = search.lower()
        log_lines = [l for l in log_lines if search_lower in l.lower()]

    content = "\n".join(log_lines[-lines:])
    return Response(
        content=content,
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename=system-logs-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.txt"},
    )


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
        select(
            WorkflowRun,
            func.coalesce(WorkflowRun.workflow_name, Workflow.name).label("workflow_name")
        )
        .outerjoin(Workflow, Workflow.id == WorkflowRun.workflow_id)
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
                        func.coalesce(WorkflowRun.workflow_name, Workflow.name).contains(q),
                        WorkflowRun.triggered_by.contains(q),
                        WorkflowRun.status.contains(q)
                    )
                )
            except ValueError:
                stmt = stmt.where(
                    or_(
                        func.coalesce(WorkflowRun.workflow_name, Workflow.name).contains(q),
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
    """Disable a schedule (soft-delete)"""
    stmt = select(Schedule).where(Schedule.id == schedule_id)
    result = await db.execute(stmt)
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    # Remove from scheduler
    scheduler_service.remove_schedule(schedule_id)

    schedule.is_enabled = False
    await db.commit()

    return {"message": "Schedule disabled successfully"}


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


@router.get("/form-uploads")
async def list_form_uploads(
    q: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all uploaded form files with uploader metadata (admin only)"""
    stmt = (
        select(FormUpload, User.username.label("uploader_username"))
        .outerjoin(User, User.id == FormUpload.uploaded_by)
    )
    if q:
        q = q.strip()
        if q:
            stmt = stmt.where(FormUpload.original_name.contains(q))

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(total_stmt)).scalar_one()

    stmt = stmt.order_by(FormUpload.created_at.desc()).limit(limit).offset(offset)
    rows = (await db.execute(stmt)).all()

    return {
        "total": total,
        "items": [
            {
                "id": upload.id,
                "original_name": upload.original_name,
                "stored_name": upload.stored_name,
                "content_type": upload.content_type,
                "size_bytes": upload.size_bytes,
                "uploaded_by": upload.uploaded_by,
                "uploader_username": uploader_username,
                "created_at": upload.created_at,
            }
            for upload, uploader_username in rows
        ],
    }


@router.post("/seed-demo-data")
async def seed_demo_data(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Seed all demo data: CMDB types/items, services, KB articles, and forms.
    
    Idempotent — safe to call multiple times; existing records are preserved.
    Admin-only.
    """
    from app.services.demo_data_service import seed_all_demo_data, commit_demo_data

    result = await seed_all_demo_data(db)
    await commit_demo_data(db)

    return {
        "success": True,
        "message": "Demo data seeded successfully",
        "details": {
            "categories": len(result.get("categories", {})),
            "services": len(result.get("services", {})),
            "groups": len(result.get("groups", {})),
            "ci_types": len(result.get("ci_types", {})),
            "kb_articles_created": result.get("kb_articles_created", 0),
            "demo_form_id": result.get("demo_form_id"),
        },
    }


@router.get("/hygiene-report")
async def get_hygiene_report(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """D4: Get hygiene report (duplicates, unreferenced content, broken refs)."""
    from app.services.hygiene_service import hygiene_service
    return await hygiene_service.get_hygiene_report(db)


@router.post("/promote/workflow/{workflow_id}")
async def promote_workflow(
    workflow_id: int,
    target_env: str = Query("production", description="Target environment (test, staging, production)"),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """E3: Promote a workflow to a target environment."""
    from app.services.promotion_service import promotion_service
    return await promotion_service.promote_workflow(db, workflow_id, target_env, current_user.id)


@router.post("/promote/form/{form_id}")
async def promote_form(
    form_id: int,
    target_env: str = Query("production", description="Target environment"),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """E3: Promote a form to a target environment."""
    from app.services.promotion_service import promotion_service
    return await promotion_service.promote_form(db, form_id, target_env, current_user.id)


@router.post("/views/regenerate/form/{form_id}")
async def regenerate_form_view(
    form_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """F1: Regenerate SQL VIEW for a form."""
    from app.services.sql_view_service import sql_view_service
    # Get form key (use name slugified)
    from sqlalchemy import select as sa_select
    from app.models.forms import Form
    result = await db.execute(sa_select(Form).where(Form.id == form_id))
    form = result.scalar_one_or_none()
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")
    key = form.name.lower().replace(" ", "_")[:50]
    return await sql_view_service.ensure_form_view(db, form_id, key)


@router.post("/views/regenerate/ci-type/{ci_type_id}")
async def regenerate_ci_type_view(
    ci_type_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """F1: Regenerate SQL VIEW for a CI type."""
    from app.services.sql_view_service import sql_view_service
    from sqlalchemy import select as sa_select
    from app.models.cmdb import CIType
    result = await db.execute(sa_select(CIType).where(CIType.id == ci_type_id))
    ci_type = result.scalar_one_or_none()
    if not ci_type:
        raise HTTPException(status_code=404, detail="CI type not found")
    return await sql_view_service.ensure_ci_type_view(db, ci_type_id, ci_type.key)


@router.get("/views")
async def list_generated_views(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """F1: List all generated SQL VIEWs."""
    from app.services.sql_view_service import sql_view_service
    return await sql_view_service.list_views(db)


@router.delete("/views/{view_name}")
async def drop_generated_view(
    view_name: str,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """F1: Drop a generated SQL VIEW."""
    from app.services.sql_view_service import sql_view_service
    return await sql_view_service.drop_view(db, view_name)

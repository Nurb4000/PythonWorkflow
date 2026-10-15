"""
Task API endpoints (P6.2: pagination support)
"""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, func
from typing import List, Optional
from sqlalchemy.orm import selectinload

from app.core.database import get_db, async_session_factory
from app.models.auth import User, Group, workflow_permissions
from app.models.schemas import Task, WorkflowRun, WorkflowStep
from app.api.auth import get_current_user, get_current_admin

router = APIRouter()


@router.get("/tasks")
async def list_tasks(
    status: Optional[str] = None,
    assigned_to: Optional[int] = None,
    workflow_run_id: Optional[int] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List tasks based on user role and permissions"""
    
    # Build base query with relationships
    stmt = (
        select(Task)
        .options(
            selectinload(Task.assigned_user),
            selectinload(Task.assigned_group),
            selectinload(Task.workflow_run)
        )
        .where(Task.is_active == True)
    )
    
    # Filter by status if provided
    if status:
        stmt = stmt.where(Task.status == status)
    
    # Filter by workflow run if provided
    if workflow_run_id:
        stmt = stmt.where(Task.workflow_run_id == workflow_run_id)
    
    # Role-based filtering
    if current_user.role == "admin":
        # Admins see all tasks
        pass
    elif current_user.role == "developer":
        # Developers see their own tasks + tasks assigned to their groups
        user_group_ids = [g.id for g in current_user.groups]
        conditions = [
            Task.assigned_to_user_id == current_user.id,
            Task.assigned_group_id.in_(user_group_ids) if user_group_ids else False
        ]
        stmt = stmt.where(or_(*conditions))
    elif current_user.role == "staff":
        # Staff see their own tasks + tasks assigned to their groups
        user_group_ids = [g.id for g in current_user.groups]
        conditions = [
            Task.assigned_to_user_id == current_user.id,
            Task.assigned_group_id.in_(user_group_ids) if user_group_ids else False
        ]
        stmt = stmt.where(or_(*conditions))
    elif current_user.role == "user":
        # Users see only their own tasks
        stmt = stmt.where(Task.assigned_to_user_id == current_user.id)
    
    # P6.2: Count total for pagination
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar()
    
    # Apply offset and limit
    stmt = stmt.offset(offset).limit(limit).order_by(Task.created_at.desc())
    
    result = await db.execute(stmt)
    tasks = result.scalars().all()
    
    return {
        "tasks": [
            {
                "id": task.id,
                "workflow_run_id": task.workflow_run_id,
                "step_id": task.step_id,
                "title": task.title,
                "description": task.description,
                "status": task.status,
                "assigned_to_user_id": task.assigned_to_user_id,
                "assigned_group_id": task.assigned_group_id,
                "form_id": task.form_id,
                "task_data": task.task_data,
                "result_data": task.result_data,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "updated_at": task.updated_at.isoformat() if task.updated_at else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                "closed_at": task.closed_at.isoformat() if task.closed_at else None,
                "assigned_user": {
                    "id": task.assigned_user.id,
                    "username": task.assigned_user.username,
                    "full_name": task.assigned_user.full_name
                } if task.assigned_user else None,
                "assigned_group": {
                    "id": task.assigned_group.id,
                    "name": task.assigned_group.name
                } if task.assigned_group else None,
                "priority": task.priority,
                "ola_pickup_met": task.ola_pickup_met,
                "ola_closure_met": task.ola_closure_met,
                "sla_response_met": task.workflow_run.sla_response_met if task.workflow_run else None,
                "sla_resolution_met": task.workflow_run.sla_resolution_met if task.workflow_run else None,
            }
            for task in tasks
        ],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/tasks/{task_id}", response_model=dict)
async def get_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a single task with full details"""
    
    stmt = (
        select(Task)
        .options(
            selectinload(Task.assigned_user),
            selectinload(Task.assigned_group)
        )
        .where(Task.id == task_id)
    )
    
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Permission check
    if current_user.role != "admin":
        user_group_ids = [g.id for g in current_user.groups]
        is_assigned_to_user = task.assigned_to_user_id == current_user.id
        is_assigned_to_group = task.assigned_group_id in user_group_ids if user_group_ids else False
        
        if not (is_assigned_to_user or is_assigned_to_group):
            raise HTTPException(status_code=403, detail="Access denied")
    
    return {
        "id": task.id,
        "workflow_run_id": task.workflow_run_id,
        "step_id": task.step_id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "assigned_to_user_id": task.assigned_to_user_id,
        "assigned_group_id": task.assigned_group_id,
        "form_id": task.form_id,
        "task_data": task.task_data,
        "result_data": task.result_data,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "closed_at": task.closed_at.isoformat() if task.closed_at else None,
        "assigned_user": {
            "id": task.assigned_user.id,
            "username": task.assigned_user.username,
            "full_name": task.assigned_user.full_name
        } if task.assigned_user else None,
        "assigned_group": {
            "id": task.assigned_group.id,
            "name": task.assigned_group.name
        } if task.assigned_group else None,
        "priority": task.priority,
        "ola_pickup_met": task.ola_pickup_met,
        "ola_closure_met": task.ola_closure_met,
    }


@router.post("/tasks/{task_id}/open")
async def open_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Open a closed task (admin only)"""
    
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    stmt = select(Task).where(Task.id == task_id)
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task.status = "open"
    task.closed_at = None
    task.updated_at = __import__('datetime', fromlist=['datetime']).datetime.now(__import__('datetime', fromlist=['timezone']).timezone.utc)
    
    await db.commit()
    await db.refresh(task)
    
    return {"message": "Task reopened", "task_id": task.id}


@router.post("/tasks/{task_id}/review")
async def review_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Move task to review status"""
    
    stmt = select(Task).where(Task.id == task_id)
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Permission check
    user_group_ids = [g.id for g in current_user.groups]
    is_assigned_to_user = task.assigned_to_user_id == current_user.id
    is_assigned_to_group = task.assigned_group_id in user_group_ids if user_group_ids else False
    
    if not (is_assigned_to_user or is_assigned_to_group or current_user.role == "admin"):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if task.status != "open":
        raise HTTPException(status_code=400, detail="Task must be in 'open' status to review")
    
    task.status = "review"
    task.updated_at = __import__('datetime', fromlist=['datetime']).datetime.now(__import__('datetime', fromlist=['timezone']).timezone.utc)
    
    await db.commit()
    
    return {"message": "Task moved to review", "task_id": task.id}


@router.post("/tasks/{task_id}/take")
async def take_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Take ownership of a task"""

    stmt = select(Task).where(Task.id == task_id)
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Permission check
    user_group_ids = [g.id for g in current_user.groups]
    is_assigned_to_user = task.assigned_to_user_id == current_user.id
    is_assigned_to_group = task.assigned_group_id in user_group_ids if user_group_ids else False

    if not (is_assigned_to_user or is_assigned_to_group or current_user.role == "admin"):
        raise HTTPException(status_code=403, detail="Access denied")

    if task.status not in ["open", "review"]:
        raise HTTPException(status_code=400, detail="Task must be in 'open' or 'review' status to take ownership")

    # H5 fix: guard against double-take — reject if already owned by someone else
    if task.assigned_to_user_id is not None and task.assigned_to_user_id != current_user.id:
        raise HTTPException(
            status_code=409,
            detail=f"Task already taken by user #{task.assigned_to_user_id}"
        )

    task.status = "owned"
    task.assigned_to_user_id = current_user.id
    task.updated_at = __import__('datetime', fromlist=['datetime']).datetime.now(__import__('datetime', fromlist=['timezone']).timezone.utc)

    # OLA pickup tracking: evaluate when task is taken
    if task.ola_pickup_target_hours is not None and task.ola_pickup_met is None and task.created_at:
        from datetime import timezone as tz
        now = __import__('datetime', fromlist=['datetime']).datetime.now(tz.utc)
        created = task.created_at.replace(tzinfo=tz.utc) if task.created_at.tzinfo is None else task.created_at
        elapsed_hours = (now - created).total_seconds() / 3600
        task.ola_pickup_met = elapsed_hours <= task.ola_pickup_target_hours

    # SLA response tracking (Phase 5): mark response met/breached when first task is taken
    if task.workflow_run_id:
        from datetime import timezone as tz
        run_stmt = select(WorkflowRun).where(WorkflowRun.id == task.workflow_run_id)
        run_result = await db.execute(run_stmt)
        run = run_result.scalar_one_or_none()
        if run and run.sla_response_target_hours is not None and run.sla_response_met is None:
            if run.started_at:
                elapsed_hours = (
                    __import__('datetime', fromlist=['datetime']).datetime.now(tz.utc) - run.started_at.replace(tzinfo=tz.utc) if run.started_at.tzinfo is None else run.started_at
                ).total_seconds() / 3600
                run.sla_response_met = elapsed_hours <= run.sla_response_target_hours

    await db.commit()

    return {"message": "Task taken", "task_id": task.id}


@router.post("/tasks/{task_id}/complete")
async def complete_task(
    task_id: int,
    result_data: dict = {},
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Complete a task"""
    
    stmt = select(Task).where(Task.id == task_id)
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Permission check
    user_group_ids = [g.id for g in current_user.groups]
    is_assigned_to_user = task.assigned_to_user_id == current_user.id
    is_assigned_to_group = task.assigned_group_id in user_group_ids if user_group_ids else False
    
    if not (is_assigned_to_user or is_assigned_to_group or current_user.role == "admin"):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if task.status != "owned":
        raise HTTPException(status_code=400, detail="Task must be in 'owned' status to complete")
    
    task.status = "completed"
    task.result_data = result_data
    task.completed_at = __import__('datetime', fromlist=['datetime']).datetime.now(__import__('datetime', fromlist=['timezone']).timezone.utc)
    task.updated_at = __import__('datetime', fromlist=['datetime']).datetime.now(__import__('datetime', fromlist=['timezone']).timezone.utc)

    # OLA closure tracking: evaluate when task is completed
    if task.ola_closure_target_hours is not None and task.ola_closure_met is None and task.created_at:
        from datetime import timezone as tz
        now = __import__('datetime', fromlist=['datetime']).datetime.now(tz.utc)
        created = task.created_at.replace(tzinfo=tz.utc) if task.created_at.tzinfo is None else task.created_at
        elapsed_hours = (now - created).total_seconds() / 3600
        task.ola_closure_met = elapsed_hours <= task.ola_closure_target_hours

    await db.commit()
    
    # Resume workflow if this task is associated with a workflow run
    if task.workflow_run_id:
        from app.services.workflow_engine import WorkflowEngine
        engine = WorkflowEngine()
        await engine.resume_workflow(task.workflow_run_id)
    
    return {"message": "Task completed", "task_id": task.id}


@router.post("/tasks/{task_id}/close")
async def close_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Close a completed task"""
    
    stmt = select(Task).where(Task.id == task_id)
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Only admin, developer, staff can close tasks
    if current_user.role not in ["admin", "developer", "staff"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="Task must be completed before closing")
    
    task.status = "closed"
    task.closed_at = __import__('datetime', fromlist=['datetime']).datetime.now(__import__('datetime', fromlist=['timezone']).timezone.utc)
    task.updated_at = __import__('datetime', fromlist=['datetime']).datetime.now(__import__('datetime', fromlist=['timezone']).timezone.utc)

    # OLA closure tracking: evaluate when task is closed
    if task.ola_closure_target_hours is not None and task.ola_closure_met is None and task.created_at:
        from datetime import timezone as tz
        now = __import__('datetime', fromlist=['datetime']).datetime.now(tz.utc)
        created = task.created_at.replace(tzinfo=tz.utc) if task.created_at.tzinfo is None else task.created_at
        elapsed_hours = (now - created).total_seconds() / 3600
        task.ola_closure_met = elapsed_hours <= task.ola_closure_target_hours

    await db.commit()
    
    return {"message": "Task closed", "task_id": task.id}


@router.post("/tasks/{task_id}/reject")
async def reject_task(
    task_id: int,
    reason: str = "",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Reject a task (move back to open)"""
    
    stmt = select(Task).where(Task.id == task_id)
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Permission check
    user_group_ids = [g.id for g in current_user.groups]
    is_assigned_to_user = task.assigned_to_user_id == current_user.id
    is_assigned_to_group = task.assigned_group_id in user_group_ids if user_group_ids else False
    
    if not (is_assigned_to_user or is_assigned_to_group or current_user.role == "admin"):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if task.status not in ["owned", "completed"]:
        raise HTTPException(status_code=400, detail="Task must be in 'owned' or 'completed' status to reject")
    
    task.status = "open"
    task.result_data = {**task.result_data, "rejection_reason": reason} if task.result_data else {"rejection_reason": reason}
    task.updated_at = __import__('datetime', fromlist=['datetime']).datetime.now(__import__('datetime', fromlist=['timezone']).timezone.utc)
    
    await db.commit()
    
    return {"message": "Task rejected", "task_id": task.id}


@router.put("/tasks/{task_id}")
async def update_task(
    task_id: int,
    task_data: dict,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update a task (admin only)"""
    
    stmt = select(Task).where(Task.id == task_id)
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Update fields
    for field in ["title", "description", "status", "assigned_to_user_id", "assigned_group_id", "form_id", "task_data", "pause_state"]:
        if field in task_data:
            setattr(task, field, task_data[field])
    
    task.updated_at = __import__('datetime', fromlist=['datetime']).datetime.now(__import__('datetime', fromlist=['timezone']).timezone.utc)
    
    await db.commit()
    await db.refresh(task)
    
    return {"message": "Task updated", "task_id": task.id}


@router.post("/tasks/{task_id}/pause")
async def pause_task(
    task_id: int,
    pause_state: str = Body(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Set task pause state (SLA/OLA pause)."""
    stmt = select(Task).where(Task.id == task_id)
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task.pause_state = pause_state
    task.updated_at = datetime.now(timezone.utc)
    await db.commit()
    
    return {"message": f"Task paused with state: {pause_state}", "task_id": task.id, "pause_state": task.pause_state}


@router.post("/tasks/{task_id}/resume")
async def resume_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Resume task (clear pause state)."""
    stmt = select(Task).where(Task.id == task_id)
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task.pause_state = "in_process"
    task.updated_at = datetime.now(timezone.utc)
    await db.commit()
    
    return {"message": "Task resumed", "task_id": task.id}


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Deactivate a task (admin only)"""

    stmt = select(Task).where(Task.id == task_id)
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.is_active = False
    await db.commit()

    return {"message": "Task deactivated", "task_id": task.id}

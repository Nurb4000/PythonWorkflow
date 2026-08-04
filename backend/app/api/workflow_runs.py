"""
API endpoints for workflow runs (P6.2: pagination support)
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.auth import User
from app.models.schemas import WorkflowRun, StepInstance
from app.api.auth import get_current_user, user_can_access_workflow
from app.schemas.workflow import WorkflowRunResponse, StepInstanceResponse

router = APIRouter()
runs_router = APIRouter()


async def _check_workflow_access(db: AsyncSession, current_user: User, workflow_id: int):
    if not await user_can_access_workflow(db, current_user, workflow_id):
        raise HTTPException(status_code=403, detail="You do not have permission to access this workflow")


@router.get("/", response_model=dict)
async def list_runs(
    workflow_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0)
):
    """List runs for a workflow with pagination (P6.2)."""
    await _check_workflow_access(db, current_user, workflow_id)
    
    stmt = (
        select(WorkflowRun)
        .where(WorkflowRun.workflow_id == workflow_id)
    )
    
    if status:
        stmt = stmt.where(WorkflowRun.status == status)
    
    # P6.2: Count total for pagination
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar()
    
    # Apply pagination
    stmt = stmt.order_by(WorkflowRun.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    runs = result.scalars().all()
    
    return {
        "runs": runs,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/{run_id}", response_model=WorkflowRunResponse)
async def get_run(
    workflow_id: int,
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get details of a specific run"""
    await _check_workflow_access(db, current_user, workflow_id)
    stmt = (
        select(WorkflowRun)
        .where(WorkflowRun.id == run_id, WorkflowRun.workflow_id == workflow_id)
    )
    result = await db.execute(stmt)
    run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    return run


@router.get("/{run_id}/steps", response_model=List[StepInstanceResponse])
async def get_run_steps(
    workflow_id: int,
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all step instances for a run"""
    await _check_workflow_access(db, current_user, workflow_id)
    stmt = (
        select(StepInstance)
        .where(StepInstance.workflow_run_id == run_id)
        .order_by(StepInstance.position)
    )
    result = await db.execute(stmt)
    instances = result.scalars().all()
    return instances


@router.delete("/{run_id}")
async def cancel_run(
    workflow_id: int,
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Cancel a running workflow run"""
    await _check_workflow_access(db, current_user, workflow_id)
    stmt = select(WorkflowRun).where(WorkflowRun.id == run_id, WorkflowRun.workflow_id == workflow_id)
    result = await db.execute(stmt)
    run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.status not in ["pending", "running"]:
        raise HTTPException(status_code=400, detail="Run cannot be cancelled")

    run.status = "cancelled"
    run.completed_at = db.func.now()
    await db.commit()

    return {"message": "Run cancelled successfully"}


@runs_router.get("/runs/{run_id}", response_model=WorkflowRunResponse)
async def get_run_by_id(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get details of a run by its id (with workflow access check)"""
    stmt = select(WorkflowRun).where(WorkflowRun.id == run_id)
    result = await db.execute(stmt)
    run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if not await user_can_access_workflow(db, current_user, run.workflow_id):
        raise HTTPException(status_code=403, detail="You do not have permission to access this run")

    return run


@runs_router.get("/runs/{run_id}/steps", response_model=List[StepInstanceResponse])
async def get_run_steps_by_id(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all step instances for a run by its id"""
    stmt = select(WorkflowRun).where(WorkflowRun.id == run_id)
    result = await db.execute(stmt)
    run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if not await user_can_access_workflow(db, current_user, run.workflow_id):
        raise HTTPException(status_code=403, detail="You do not have permission to access this run")

    stmt = (
        select(StepInstance)
        .where(StepInstance.workflow_run_id == run_id)
        .order_by(StepInstance.position)
    )
    result = await db.execute(stmt)
    instances = result.scalars().all()
    return instances

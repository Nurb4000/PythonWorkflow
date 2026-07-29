"""
API endpoints for workflow runs
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.schemas import WorkflowRun, StepInstance
from app.schemas.workflow import WorkflowRunResponse, StepInstanceResponse

router = APIRouter()


@router.get("/", response_model=List[WorkflowRunResponse])
async def list_runs(workflow_id: int, db: AsyncSession = Depends(get_db)):
    """List all runs for a workflow"""
    stmt = (
        select(WorkflowRun)
        .where(WorkflowRun.workflow_id == workflow_id)
        .order_by(WorkflowRun.created_at.desc())
    )
    result = await db.execute(stmt)
    runs = result.scalars().all()
    return runs


@router.get("/{run_id}", response_model=WorkflowRunResponse)
async def get_run(workflow_id: int, run_id: int, db: AsyncSession = Depends(get_db)):
    """Get details of a specific run"""
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
async def get_run_steps(workflow_id: int, run_id: int, db: AsyncSession = Depends(get_db)):
    """Get all step instances for a run"""
    stmt = (
        select(StepInstance)
        .where(StepInstance.workflow_run_id == run_id)
        .order_by(StepInstance.position)
    )
    result = await db.execute(stmt)
    instances = result.scalars().all()
    return instances


@router.delete("/{run_id}")
async def cancel_run(workflow_id: int, run_id: int, db: AsyncSession = Depends(get_db)):
    """Cancel a running workflow run"""
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

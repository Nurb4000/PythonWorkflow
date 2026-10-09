"""
API endpoints for workflow runs (P6.2: pagination support)
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.auth import User
from app.models.schemas import Workflow, WorkflowRun, StepInstance, WorkflowStep
from app.api.auth import get_current_user, user_can_access_workflow
from app.schemas.workflow import WorkflowRunResponse, StepInstanceResponse

router = APIRouter()
runs_router = APIRouter()


async def _check_workflow_access(db: AsyncSession, current_user: User, workflow_id: int) -> None:
    if not await user_can_access_workflow(db, current_user, workflow_id):
        raise HTTPException(status_code=403, detail="You do not have permission to access this workflow")


@router.get("/", response_model=dict)
async def list_runs(
    workflow_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> Dict[str, Any]:
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
    db: AsyncSession = Depends(get_db),
) -> Dict[str, str]:
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
    db: AsyncSession = Depends(get_db),
) -> WorkflowRun:
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


@runs_router.delete("/runs/{run_id}")
async def cancel_run_global(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, str]:
    """Cancel a running workflow run (global endpoint, no workflow id needed)."""
    stmt = select(WorkflowRun).where(WorkflowRun.id == run_id)
    result = await db.execute(stmt)
    run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if not await user_can_access_workflow(db, current_user, run.workflow_id):
        raise HTTPException(status_code=403, detail="You do not have permission to cancel this run")

    if run.status not in ["pending", "running"]:
        raise HTTPException(status_code=400, detail=f"Run cannot be cancelled (status: {run.status})")

    from datetime import datetime
    run.status = "cancelled"
    run.completed_at = datetime.utcnow()
    await db.commit()

    return {"message": "Run cancelled successfully", "id": run.id}


@runs_router.post("/runs/{run_id}/rerun")
async def rerun_run(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Re-trigger the same workflow with the original input data."""
    from app.services.workflow_engine import WorkflowEngine
    from app.schemas.workflow import WorkflowRunCreate

    stmt = select(WorkflowRun).where(WorkflowRun.id == run_id)
    result = await db.execute(stmt)
    run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.workflow_id is None:
        raise HTTPException(status_code=400, detail="Cannot re-run: original workflow has been deleted")

    if not await user_can_access_workflow(db, current_user, run.workflow_id):
        raise HTTPException(status_code=403, detail="You do not have permission to re-run this workflow")

    engine = WorkflowEngine()
    new_run = await engine.trigger_workflow(
        db,
        run.workflow_id,
        WorkflowRunCreate(
            input_data=run.input_data or {},
            triggered_by=f"rerun:{current_user.username}",
            timeout_seconds=run.timeout_seconds,
            max_retries=run.max_retries,
            failure_hooks=run.failure_hooks or [],
        ),
    )

    return WorkflowRunResponse.model_validate(new_run)


@runs_router.get("/runs/{run_id}/inspector")
async def get_run_inspector(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Combined run + steps + workflow graph payload for the Run Inspector.

    Returns a single response with everything needed to render the graph view:
    - run: WorkflowRunResponse
    - steps: list of StepInstanceResponse (enriched)
    - workflow: {id, name, environment} or null if deleted
    - graph: {start_step_ids, steps: [...]} — step definitions for rendering
      (falls back to instance snapshots when the workflow is gone)
    """
    # 1. Fetch run + access check
    stmt = select(WorkflowRun).where(WorkflowRun.id == run_id)
    result = await db.execute(stmt)
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if not await user_can_access_workflow(db, current_user, run.workflow_id):
        raise HTTPException(status_code=403, detail="You do not have permission to access this run")

    # 2. Fetch step instances
    inst_stmt = (
        select(StepInstance)
        .where(StepInstance.workflow_run_id == run_id)
        .order_by(StepInstance.position)
    )
    inst_result = await db.execute(inst_stmt)
    instances = inst_result.scalars().all()

    # 3. Workflow info + graph payload
    workflow_info: Optional[Dict[str, Any]] = None
    graph_steps: List[Dict[str, Any]] = []
    start_step_ids: List[int] = []

    if run.workflow_id is not None:
        wf_stmt = select(Workflow).where(Workflow.id == run.workflow_id).options(selectinload(Workflow.steps))
        wf_result = await db.execute(wf_stmt)
        workflow = wf_result.scalar_one_or_none()
        if workflow:
            workflow_info = {
                "id": workflow.id,
                "name": workflow.name,
                "environment": workflow.environment,
            }
            config = workflow.config or {}
            start_step_ids = config.get("start_step_ids") or []
            for ws in workflow.steps:
                d = ws.definition or {}
                graph_steps.append({
                    "id": ws.id,
                    "step_type": ws.step_type,
                    "title": ws.title or "",
                    "description": ws.description or "",
                    "position": ws.position,
                    "next_step_ids": d.get("next_step_ids") or [],
                    "next_step_id": d.get("next_step_id"),
                    "routes": d.get("routes") or [],
                    "default_target_step_id": d.get("default_target_step_id"),
                    "pos_x": d.get("pos_x"),
                    "pos_y": d.get("pos_y"),
                    "definition": d,
                })

    # 4. If workflow is gone, build graph from instance snapshots
    if not graph_steps:
        for inst in instances:
            d = inst.step_definition or {}
            graph_steps.append({
                "id": inst.id,
                "step_type": inst.step_type or "",
                "title": inst.title or "",
                "description": inst.description or "",
                "position": inst.position,
                "next_step_ids": d.get("next_step_ids") or [],
                "next_step_id": d.get("next_step_id"),
                "routes": d.get("routes") or [],
                "default_target_step_id": d.get("default_target_step_id"),
                "pos_x": d.get("pos_x"),
                "pos_y": d.get("pos_y"),
                "definition": d,
            })

    return {
        "run": WorkflowRunResponse.model_validate(run),
        "steps": [StepInstanceResponse.model_validate(i) for i in instances],
        "workflow": workflow_info,
        "graph": {
            "start_step_ids": start_step_ids,
            "steps": graph_steps,
        },
    }

"""
API endpoints for workflow management
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List

from app.core.database import get_db
from app.models.schemas import Workflow, WorkflowStep, WorkflowRun
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowUpdate,
    WorkflowResponse,
    WorkflowListResponse,
    StepResponse,
    WorkflowRunCreate,
    WorkflowRunResponse
)
from app.services.workflow_engine import WorkflowEngine

router = APIRouter()
engine = WorkflowEngine()


@router.post("/", response_model=WorkflowResponse)
async def create_workflow(workflow_data: WorkflowCreate, db: AsyncSession = Depends(get_db)):
    """Create a new workflow"""
    try:
        workflow = await engine.create_workflow(db, workflow_data)
        return workflow
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=List[WorkflowListResponse])
async def list_workflows(db: AsyncSession = Depends(get_db)):
    """List all workflows with counts"""
    stmt = (
        select(Workflow.id, Workflow.name, Workflow.description, Workflow.is_active, Workflow.created_at,
               func.count(WorkflowStep.id).label('steps_count'),
               func.count(WorkflowRun.id).label('runs_count'))
        .outerjoin(WorkflowStep, WorkflowStep.workflow_id == Workflow.id)
        .outerjoin(WorkflowRun, WorkflowRun.workflow_id == Workflow.id)
        .group_by(Workflow.id)
    )
    result = await db.execute(stmt)
    rows = result.all()
    
    workflows = []
    for row in rows:
        workflows.append({
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "is_active": row.is_active,
            "steps_count": row.steps_count,
            "runs_count": row.runs_count,
            "created_at": row.created_at
        })
    return workflows


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: int, db: AsyncSession = Depends(get_db)):
    """Get workflow details with steps"""
    stmt = (
        select(Workflow)
        .where(Workflow.id == workflow_id)
        .options(selectinload(Workflow.steps))
    )
    result = await db.execute(stmt)
    workflow = result.scalar_one_or_none()
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    return workflow


@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(workflow_id: int, workflow_data: WorkflowUpdate, db: AsyncSession = Depends(get_db)):
    """Update a workflow"""
    workflow = await engine.update_workflow(db, workflow_id, workflow_data)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a workflow"""
    success = await engine.delete_workflow(db, workflow_id)
    if not success:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"message": "Workflow deleted successfully"}


@router.post("/{workflow_id}/steps", response_model=StepResponse)
async def add_step(workflow_id: int, step_data: dict, db: AsyncSession = Depends(get_db)):
    """Add a step to a workflow"""
    stmt = select(Workflow).where(Workflow.id == workflow_id)
    result = await db.execute(stmt)
    workflow = result.scalar_one_or_none()
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    step = WorkflowStep(
        workflow_id=workflow_id,
        step_type=step_data["step_type"],
        definition=step_data.get("definition", {}),
        position=step_data.get("position", 0),
        condition_expr=step_data.get("condition_expr", ""),
        is_enabled=step_data.get("is_enabled", True)
    )
    db.add(step)
    await db.commit()
    await db.refresh(step)
    return step


@router.post("/{workflow_id}/run", response_model=WorkflowRunResponse)
async def trigger_run(workflow_id: int, run_data: WorkflowRunCreate, db: AsyncSession = Depends(get_db)):
    """Trigger a workflow run"""
    try:
        run = await engine.trigger_workflow(db, workflow_id, run_data)
        return run
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

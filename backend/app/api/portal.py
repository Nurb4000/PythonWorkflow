"""
Portal API endpoints for user/staff workflow access
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_
from typing import List, Optional
from sqlalchemy.orm import selectinload

from fastapi import Depends
from app.core.database import get_db
from app.models.auth import User, Group, workflow_permissions
from app.models.schemas import Workflow
from app.services.auth_service import auth_service
from app.api.auth import get_current_user

router = APIRouter()


@router.get("/portal/workflows")
async def get_available_workflows(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get workflows available to the current user based on their role and groups (P3.3)"""
    
    # Published + active workflows only
    base = and_(Workflow.is_active == True, Workflow.is_published == True, Workflow.portal_visible == True)
    
    # Admins can see all published workflows
    if current_user.role in ("admin", "developer"):
        stmt = select(Workflow).where(base)
    else:
        # Get workflows where user's groups have permission
        user_group_ids = [g.id for g in current_user.groups]
        
        if not user_group_ids:
            # Users without groups can only see published workflows marked for all
            stmt = select(Workflow).where(
                base,
                Workflow.environment == "production"
            )
        else:
            # Users with groups can see workflows accessible to any of their groups
            permitted_wf_ids = (
                select(workflow_permissions.c.workflow_id)
                .where(workflow_permissions.c.group_id.in_(user_group_ids))
                .distinct()
            )
            stmt = select(Workflow).where(
                base,
                or_(
                    Workflow.id.in_(permitted_wf_ids),
                    Workflow.environment == "production"
                )
            )
    
    stmt = stmt.order_by(Workflow.portal_order.asc(), Workflow.name.asc())
    result = await db.execute(stmt)
    workflows = result.scalars().all()
    
    return [
        {
            "id": w.id,
            "name": w.name,
            "description": w.description,
            "environment": w.environment,
            "is_published": w.is_published,
            "portal_icon": w.portal_icon or "",
            "portal_order": w.portal_order or 0,
            "portal_visible": w.portal_visible,
            "portal_link_url": (w.config or {}).get("portal_link_url", ""),
            "entry_form_id": w.entry_form_id,  # P3.3
        }
        for w in workflows
    ]


@router.post("/portal/workflows/{workflow_id}/run")
async def run_workflow(
    workflow_id: int,
    input_data: Optional[dict] = {},
    priority: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Run a workflow (users and staff only)"""

    # Verify workflow is accessible
    stmt = select(Workflow).where(Workflow.id == workflow_id).options(selectinload(Workflow.service))
    result = await db.execute(stmt)
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if not workflow.is_active:
        raise HTTPException(status_code=400, detail="Workflow is not active")

    # Check permissions
    if current_user.role in ["user", "staff"]:
        # Verify workflow is published and visible on the portal
        if not workflow.is_published or not workflow.portal_visible:
            raise HTTPException(status_code=403, detail="Workflow not available for portal use")

        # Production workflows are accessible to all; otherwise check group permissions
        if workflow.environment != "production":
            user_group_ids = [g.id for g in current_user.groups]
            if user_group_ids:
                stmt = (
                    select(workflow_permissions)
                    .where(
                        workflow_permissions.c.workflow_id == workflow_id,
                        workflow_permissions.c.group_id.in_(user_group_ids)
                    )
                )
                result = await db.execute(stmt)
                if not result.fetchone():
                    raise HTTPException(status_code=403, detail="You don't have permission to run this workflow")
            else:
                raise HTTPException(status_code=403, detail="You don't have permission to run this workflow")

    # Trigger the workflow
    from app.schemas.workflow import WorkflowRunCreate
    from app.services.workflow_engine import WorkflowEngine

    engine = WorkflowEngine()
    run_data = WorkflowRunCreate(
        input_data=input_data or {},
        triggered_by=f"user:{current_user.id}",
        priority=priority,
        service_id=workflow.service_id,
    )

    run = await engine.trigger_workflow(db, workflow_id, run_data)

    return {
        "success": True,
        "run_id": run.id,
        "message": "Workflow started successfully"
    }


@router.get("/portal/my-runs")
async def get_my_runs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get workflows runs initiated by the current user"""
    
    from app.models.schemas import WorkflowRun
    
    stmt = (
        select(WorkflowRun)
        .where(WorkflowRun.triggered_by.like(f"user:{current_user.id}%"))
        .order_by(WorkflowRun.created_at.desc())
        .limit(100)
    )
    
    result = await db.execute(stmt)
    runs = result.scalars().all()
    
    return [
        {
            "id": r.id,
            "workflow_id": r.workflow_id,
            "workflow_name": r.workflow_name or "",
            "status": r.status,
            "triggered_by": r.triggered_by,
            "started_at": r.started_at,
            "completed_at": r.completed_at,
            "error_message": r.error_message or "",
            "created_at": r.created_at,
        }
        for r in runs
    ]


@router.get("/portal/my-tasks")
async def get_my_tasks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get open tasks assigned to the current user (P3.3)"""
    
    from app.models.schemas import Task
    
    # Get tasks assigned to this user that are still open/owned
    stmt = select(Task).where(
        or_(
            Task.assigned_to_user_id == current_user.id,
            and_(Task.assigned_group_id != None, Task.assigned_to_user_id == None)  # noqa: E711
        ),
        Task.status.in_(["open", "owned"])
    )
    
    # If user has groups, include group-assigned tasks
    user_group_ids = [g.id for g in current_user.groups]
    if user_group_ids:
        stmt = stmt.where(
            or_(
                Task.assigned_to_user_id == current_user.id,
                Task.assigned_group_id.in_(user_group_ids)
            )
        )
    
    stmt = stmt.order_by(Task.created_at.desc()).limit(50)
    result = await db.execute(stmt)
    tasks = result.scalars().all()
    
    return [
        {
            "id": t.id,
            "title": t.title,
            "description": t.description,
            "status": t.status,
            "workflow_run_id": t.workflow_run_id,
            "step_id": t.step_id,
            "created_at": t.created_at,
            "completed_at": t.completed_at,
        }
        for t in tasks
    ]


@router.get("/portal/search/workflows")
async def search_workflows(
    query: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Search workflows (limited to user's permissions)"""
    
    from app.models.schemas import Workflow
    
    stmt = select(Workflow).where(
        or_(
            Workflow.name.contains(query),
            Workflow.description.contains(query)
        ),
        Workflow.is_active == True
    )
    
    # Filter by permissions for non-admins
    if current_user.role != "admin":
        user_group_ids = [g.id for g in current_user.groups]
        if user_group_ids:
            stmt = stmt.where(
                Workflow.id.in_(
                    select(workflow_permissions.c.workflow_id).where(
                        workflow_permissions.c.group_id.in_(user_group_ids)
                    )
                )
            )
        else:
            stmt = stmt.where(Workflow.is_published == True)
    
    result = await db.execute(stmt)
    workflows = result.scalars().all()
    
    return [
        {
            "id": w.id,
            "name": w.name,
            "description": w.description,
            "environment": w.environment
        }
        for w in workflows
    ]




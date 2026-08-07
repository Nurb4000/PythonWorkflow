"""
API endpoints for workflow management
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import List, Optional

from app.core.database import get_db
from app.models.auth import User, Group
from app.models.schemas import Workflow, WorkflowStep, WorkflowRun, Task
from app.models.forms import Form, FormSubmission
from app.api.auth import get_current_user, get_current_developer, user_can_access_workflow
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowUpdate,
    WorkflowRunCreate,
    WorkflowRunResponse
)
from app.services.workflow_engine import WorkflowEngine

router = APIRouter()
engine = WorkflowEngine()


def _step_to_dict(step: WorkflowStep) -> dict:
    return {
        "id": step.id,
        "workflow_id": step.workflow_id,
        "step_type": step.step_type,
        "definition": step.definition,
        "position": step.position,
        "condition_expr": step.condition_expr,
        "is_enabled": step.is_enabled,
        "title": step.title or "",
        "description": step.description or "",
        "created_at": step.created_at
    }


def _workflow_to_response(workflow: Workflow) -> dict:
    return {
        "id": workflow.id,
        "name": workflow.name,
        "description": workflow.description,
        "version": workflow.version,
        "is_active": workflow.is_active,
        "is_published": workflow.is_published,
        "environment": workflow.environment,
        "config": workflow.config or {},
        "portal_icon": workflow.portal_icon or "",
        "portal_order": workflow.portal_order or 0,
        "portal_visible": workflow.portal_visible,
        "created_at": workflow.created_at,
        "updated_at": workflow.updated_at,
        "steps": [_step_to_dict(s) for s in workflow.steps],
        "allowed_groups": [{"id": g.id, "name": g.name} for g in workflow.allowed_groups]
    }


@router.post("/")
async def create_workflow(
    workflow_data: WorkflowCreate,
    developer: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db)
):
    """Create a new workflow (admin/developer only)"""
    try:
        workflow = await engine.create_workflow(
            db, workflow_data,
            created_by=developer.id,
            allowed_group_ids=workflow_data.allowed_group_ids
        )
        # Reload with steps and groups for response
        stmt = (
            select(Workflow)
            .where(Workflow.id == workflow.id)
            .options(selectinload(Workflow.steps), selectinload(Workflow.allowed_groups))
        )
        result = await db.execute(stmt)
        return _workflow_to_response(result.scalar_one())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
async def list_workflows(
    search: Optional[str] = Query(None, description="Search by name or description"),
    status: Optional[str] = Query(None, description="Filter by status: active, inactive, published, draft"),
    sort_by: Optional[str] = Query("name", description="Sort field: name, created_at, runs_count, steps_count, portal_order"),
    sort_order: Optional[str] = Query("asc", description="Sort direction: asc, desc"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List workflows with counts (restricted by group permissions unless admin/developer).

    Supports search, filter, and sort query parameters.
    """
    stmt = (
        select(Workflow.id, Workflow.name, Workflow.description, Workflow.is_active, Workflow.created_at,
               Workflow.is_published, Workflow.environment,
               Workflow.portal_icon, Workflow.portal_order, Workflow.portal_visible,
               func.count(WorkflowStep.id).label('steps_count'),
               func.count(WorkflowRun.id).label('runs_count'))
        .outerjoin(WorkflowStep, WorkflowStep.workflow_id == Workflow.id)
        .outerjoin(WorkflowRun, WorkflowRun.workflow_id == Workflow.id)
        .group_by(Workflow.id)
    )

    # Search filter
    if search:
        search_pattern = f"%{search}%"
        stmt = stmt.where(
            (Workflow.name.ilike(search_pattern)) |
            (Workflow.description.ilike(search_pattern))
        )

    # Status filter
    if status:
        status_lower = status.lower()
        if status_lower == "active":
            stmt = stmt.where(Workflow.is_active == True)
        elif status_lower == "inactive":
            stmt = stmt.where(Workflow.is_active == False)
        elif status_lower == "published":
            stmt = stmt.where(Workflow.is_published == True)
        elif status_lower == "draft":
            stmt = stmt.where(Workflow.is_published == False)

    # Non-admin/developer users only see workflows permitted to their groups
    if current_user.role not in ("admin", "developer"):
        user_group_ids = {g.id for g in current_user.groups}
        wf_stmt = select(Workflow).options(selectinload(Workflow.allowed_groups))
        result = await db.execute(wf_stmt)
        permitted_ids = [
            w.id for w in result.scalars().all()
            if user_group_ids & {g.id for g in w.allowed_groups}
        ]
        if not permitted_ids:
            return []
        stmt = stmt.where(Workflow.id.in_(permitted_ids))

    # Sorting
    valid_sort_fields = {
        "name": Workflow.name,
        "created_at": Workflow.created_at,
        "runs_count": func.count(WorkflowRun.id),
        "steps_count": func.count(WorkflowStep.id),
        "portal_order": Workflow.portal_order,
    }
    sort_col = valid_sort_fields.get(sort_by or "name", Workflow.name)
    stmt = stmt.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())

    result = await db.execute(stmt)
    rows = result.all()

    # Load allowed groups for each workflow
    group_stmt = select(Workflow).options(selectinload(Workflow.allowed_groups))
    if current_user.role not in ("admin", "developer"):
        group_stmt = group_stmt.where(Workflow.id.in_([r.id for r in rows]))
    result = await db.execute(group_stmt)
    groups_by_wf = {w.id: w.allowed_groups for w in result.scalars().all()}

    workflows = []
    for row in rows:
        workflows.append({
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "is_active": row.is_active,
            "is_published": row.is_published,
            "environment": row.environment,
            "portal_icon": row.portal_icon or "",
            "portal_order": row.portal_order or 0,
            "portal_visible": row.portal_visible,
            "steps_count": row.steps_count,
            "runs_count": row.runs_count,
            "created_at": row.created_at,
            "allowed_groups": [{"id": g.id, "name": g.name} for g in groups_by_wf.get(row.id, [])]
        })
    return workflows


@router.get("/{workflow_id}")
async def get_workflow(
    workflow_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get workflow details with steps"""
    stmt = (
        select(Workflow)
        .where(Workflow.id == workflow_id)
        .options(selectinload(Workflow.steps), selectinload(Workflow.allowed_groups))
    )
    result = await db.execute(stmt)
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if not await user_can_access_workflow(db, current_user, workflow_id):
        raise HTTPException(status_code=403, detail="You do not have permission to access this workflow")

    return _workflow_to_response(workflow)


@router.put("/{workflow_id}")
async def update_workflow(
    workflow_id: int,
    workflow_data: WorkflowUpdate,
    developer: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db)
):
    """Update a workflow (admin/developer only)"""
    workflow = await engine.update_workflow(db, workflow_id, workflow_data)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    # Reload with steps for response
    stmt = (
        select(Workflow)
        .where(Workflow.id == workflow.id)
        .options(selectinload(Workflow.steps), selectinload(Workflow.allowed_groups))
    )
    result = await db.execute(stmt)
    return _workflow_to_response(result.scalar_one())


@router.get("/{workflow_id}/associated-forms")
async def get_workflow_associated_forms(
    workflow_id: int,
    developer: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db)
):
    """Get forms associated with a workflow (entry form, step forms, task forms)."""
    stmt = select(Workflow).where(Workflow.id == workflow_id).options(
        selectinload(Workflow.steps)
    )
    result = await db.execute(stmt)
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    form_ids = set()

    # Entry form
    if workflow.entry_form_id:
        form_ids.add(workflow.entry_form_id)

    # Forms referenced in step definitions (form and readonly_form steps)
    for step in workflow.steps:
        defn = step.definition or {}
        if step.step_type in ("form", "readonly_form") and defn.get("form_id"):
            form_ids.add(defn["form_id"])
        # Human task / approval steps may reference forms
        if step.step_type in ("human_task", "approval") and defn.get("form_id"):
            form_ids.add(defn["form_id"])

    # Forms referenced in tasks created by this workflow's runs
    if form_ids:
        task_stmt = select(Task.form_id).where(
            Task.workflow_run_id.in_(
                select(WorkflowRun.id).where(WorkflowRun.workflow_id == workflow_id)
            ),
            Task.form_id.isnot(None),
            Task.form_id.notin_(form_ids)
        )
    else:
        task_stmt = select(Task.form_id).where(
            Task.workflow_run_id.in_(
                select(WorkflowRun.id).where(WorkflowRun.workflow_id == workflow_id)
            ),
            Task.form_id.isnot(None)
        )
    task_result = await db.execute(task_stmt)
    for row in task_result.scalars().all():
        if row:
            form_ids.add(row)

    # Load form details
    forms = []
    if form_ids:
        form_stmt = select(Form).where(Form.id.in_(form_ids))
        form_result = await db.execute(form_stmt)
        for f in form_result.scalars().all():
            forms.append({
                "id": f.id,
                "name": f.name,
                "description": f.description or "",
            })

    return {
        "workflow_id": workflow_id,
        "forms": forms,
        "form_count": len(forms),
    }


@router.delete("/{workflow_id}")
async def delete_workflow(
    workflow_id: int,
    delete_forms: bool = Query(False),
    developer: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db)
):
    """Delete a workflow (admin/developer only). Set delete_forms=true to also remove associated forms."""
    stmt = select(Workflow).where(Workflow.id == workflow_id).options(
        selectinload(Workflow.steps)
    )
    result = await db.execute(stmt)
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Collect associated form IDs
    form_ids = set()
    if workflow.entry_form_id:
        form_ids.add(workflow.entry_form_id)
    for step in workflow.steps:
        defn = step.definition or {}
        if defn.get("form_id"):
            form_ids.add(defn["form_id"])

    # Also check tasks from workflow runs
    if form_ids:
        task_stmt = select(Task.form_id).where(
            Task.workflow_run_id.in_(
                select(WorkflowRun.id).where(WorkflowRun.workflow_id == workflow_id)
            ),
            Task.form_id.isnot(None),
            Task.form_id.notin_(form_ids)
        )
    else:
        task_stmt = select(Task.form_id).where(
            Task.workflow_run_id.in_(
                select(WorkflowRun.id).where(WorkflowRun.workflow_id == workflow_id)
            ),
            Task.form_id.isnot(None)
        )
    task_result = await db.execute(task_stmt)
    for row in task_result.scalars().all():
        if row:
            form_ids.add(row)

    # Delete associated schedules first (no cascade from Workflow)
    from sqlalchemy import delete as sa_delete
    from app.models.schemas import Schedule
    await db.execute(sa_delete(Schedule).where(Schedule.workflow_id == workflow_id))

    # Delete tasks associated with this workflow's runs (no cascade to tasks)
    await db.execute(
        sa_delete(Task).where(
            Task.workflow_run_id.in_(
                select(WorkflowRun.id).where(WorkflowRun.workflow_id == workflow_id)
            )
        )
    )

    # Delete the workflow (cascade handles steps, runs, etc.)
    await db.delete(workflow)
    await db.commit()

    # Optionally delete associated forms
    deleted_form_count = 0
    if delete_forms and form_ids:
        from sqlalchemy import delete as sa_delete
        for fid in form_ids:
            await db.execute(sa_delete(FormSubmission).where(FormSubmission.form_id == fid))
            result = await db.execute(sa_delete(Form).where(Form.id == fid))
            deleted_form_count += result.rowcount
        await db.commit()

    return {
        "message": "Workflow deleted successfully",
        "forms_deleted": deleted_form_count,
    }


@router.put("/{workflow_id}/permissions")
async def set_workflow_permissions(
    workflow_id: int,
    group_ids: List[int],
    developer: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db)
):
    """Set which groups may view/run a workflow (admin/developer only)"""
    from sqlalchemy import delete, insert
    from app.models.auth import workflow_permissions

    stmt = select(Workflow).where(Workflow.id == workflow_id)
    result = await db.execute(stmt)
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    stmt = select(Group).where(Group.id.in_(group_ids))
    result = await db.execute(stmt)
    groups = result.scalars().all()
    if len(groups) != len(set(group_ids)):
        raise HTTPException(status_code=400, detail="One or more groups not found")

    await db.execute(delete(workflow_permissions).where(workflow_permissions.c.workflow_id == workflow_id))
    if group_ids:
        await db.execute(
            insert(workflow_permissions),
            [{"workflow_id": workflow_id, "group_id": g.id} for g in groups]
        )
    await db.commit()

    return {
        "workflow_id": workflow_id,
        "allowed_groups": [{"id": g.id, "name": g.name} for g in groups]
    }


@router.post("/{workflow_id}/steps")
async def add_step(
    workflow_id: int,
    step_data: dict,
    developer: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db)
):
    """Add a step to a workflow (admin/developer only)"""
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
    return _step_to_dict(step)


@router.put("/{workflow_id}/steps/{step_id}")
async def update_step(
    workflow_id: int,
    step_id: int,
    step_data: dict,
    developer: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db)
):
    """Update a specific step (admin/developer only)"""
    stmt = select(WorkflowStep).where(
        WorkflowStep.id == step_id,
        WorkflowStep.workflow_id == workflow_id
    )
    result = await db.execute(stmt)
    step = result.scalar_one_or_none()

    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    if "step_type" in step_data:
        step.step_type = step_data["step_type"]
    if "definition" in step_data:
        step.definition = step_data["definition"]
    if "condition_expr" in step_data:
        step.condition_expr = step_data["condition_expr"]
    if "is_enabled" in step_data:
        step.is_enabled = step_data["is_enabled"]
    if "position" in step_data:
        step.position = step_data["position"]
    if "title" in step_data:
        step.title = step_data["title"]
    if "description" in step_data:
        step.description = step_data["description"]

    await db.commit()
    await db.refresh(step)
    return _step_to_dict(step)


@router.delete("/{workflow_id}/steps/{step_id}")
async def delete_step(
    workflow_id: int,
    step_id: int,
    developer: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db)
):
    """Delete a step from a workflow (admin/developer only)"""
    stmt = select(WorkflowStep).where(
        WorkflowStep.id == step_id,
        WorkflowStep.workflow_id == workflow_id
    )
    result = await db.execute(stmt)
    step = result.scalar_one_or_none()

    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    await db.delete(step)
    await db.commit()
    return {"message": "Step deleted successfully"}


@router.post("/{workflow_id}/run", response_model=WorkflowRunResponse)
async def trigger_run(
    workflow_id: int,
    run_data: WorkflowRunCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Trigger a workflow run"""
    if not await user_can_access_workflow(db, current_user, workflow_id):
        raise HTTPException(status_code=403, detail="You do not have permission to run this workflow")
    try:
        run = await engine.trigger_workflow(db, workflow_id, run_data)
        return run
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

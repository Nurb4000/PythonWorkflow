"""
Service Management API — SERVICE_MANAGEMENT_PLAN Phase 1
"""
import re
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import Optional

from app.core.database import get_db
from app.models.auth import User, Group
from app.models.schemas import Workflow, WorkflowStep, WorkflowRun
from app.models.services import Service, Category
from app.api.auth import get_current_user, get_current_admin
from app.schemas.services import (
    CategoryCreate,
    CategoryUpdate,
    CategoryResponse,
    ServiceCreate,
    ServiceUpdate,
    ServiceResponse,
)

router = APIRouter()


# --- Helpers ---

def _slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    slug = re.sub(r'[^\w\s-]', '', text.lower()).strip().replace(' ', '-').replace('_', '-')
    return slug or 'service'


def _category_to_dict(cat: Category, count: int = 0) -> dict:
    return {
        "id": cat.id,
        "name": cat.name,
        "key": cat.key,
        "icon": cat.icon or "",
        "description": cat.description or "",
        "sort_order": cat.sort_order or 0,
        "is_active": cat.is_active,
        "service_count": count,
    }


def _service_to_dict(svc: Service, wf_count: int = 0) -> dict:
    result = {
        "id": svc.id,
        "name": svc.name,
        "key": svc.key,
        "description": svc.description or "",
        "icon": svc.icon or "",
        "category_id": svc.category_id,
        "owner_id": svc.owner_id,
        "support_group_id": svc.support_group_id,
        "is_active": svc.is_active,
        "sort_order": svc.sort_order or 0,
        "custom_data": svc.custom_data or {},
        "workflow_count": wf_count,
        "created_at": svc.created_at,
        "updated_at": svc.updated_at,
    }
    if svc.owner:
        result["owner"] = {"id": svc.owner.id, "username": svc.owner.username, "full_name": svc.owner.full_name}
    if svc.support_group:
        result["support_group"] = {"id": svc.support_group.id, "name": svc.support_group.name}
    if svc.category:
        result["category"] = {
            "id": svc.category.id,
            "name": svc.category.name,
            "key": svc.category.key,
            "icon": svc.category.icon or "",
        }
    return result


# --- Categories API ---

@router.get("/categories")
async def list_categories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all categories with service counts."""
    stmt = select(Category).where(Category.is_active == True).order_by(Category.sort_order.asc(), Category.name.asc())
    result = await db.execute(stmt)
    categories = result.scalars().all()

    # Count services per category
    count_stmt = select(Category.id, func.count(Service.id)).outerjoin(Service).group_by(Category.id)
    count_result = await db.execute(count_stmt)
    counts = {row[0]: row[1] for row in count_result.all()}

    return [_category_to_dict(cat, counts.get(cat.id, 0)) for cat in categories]


@router.post("/categories")
async def create_category(
    data: CategoryCreate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a new category (admin only)."""
    key = data.key or _slugify(data.name)

    existing = await db.execute(select(Category).where((Category.name == data.name) | (Category.key == key)))
    existing = existing.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Category with this name or key already exists")

    cat = Category(
        name=data.name,
        key=key,
        icon=data.icon or "",
        description=data.description or "",
        sort_order=data.sort_order,
    )
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return _category_to_dict(cat)


@router.put("/categories/{category_id}")
async def update_category(
    category_id: int,
    data: CategoryUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update a category (admin only)."""
    stmt = select(Category).where(Category.id == category_id)
    result = await db.execute(stmt)
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    if data.name is not None and data.name != cat.name:
        existing = await db.execute(select(Category).where(Category.name == data.name, Category.id != category_id))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Category with this name already exists")
        cat.name = data.name

    if data.key is not None and data.key != cat.key:
        existing = await db.execute(select(Category).where(Category.key == data.key, Category.id != category_id))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Category with this key already exists")
        cat.key = data.key

    if data.icon is not None:
        cat.icon = data.icon
    if data.description is not None:
        cat.description = data.description
    if data.sort_order is not None:
        cat.sort_order = data.sort_order
    if data.is_active is not None:
        cat.is_active = data.is_active

    await db.commit()
    await db.refresh(cat)
    return _category_to_dict(cat)


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Soft-delete a category (admin only)."""
    stmt = select(Category).where(Category.id == category_id)
    result = await db.execute(stmt)
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    cat.is_active = False
    await db.commit()
    return {"message": "Category deactivated"}


# --- Services API ---

@router.get("/services")
async def list_services(
    search: Optional[str] = Query(None),
    category_id: Optional[int] = Query(None),
    include_inactive: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List services. Non-admins see active only unless they're admin."""
    stmt = select(Service)
    if not include_inactive and current_user.role != "admin":
        stmt = stmt.where(Service.is_active == True)
    elif not include_inactive:
        stmt = stmt.where(Service.is_active == True)

    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            (Service.name.ilike(pattern)) | (Service.description.ilike(pattern)) | (Service.key.ilike(pattern))
        )
    if category_id is not None:
        stmt = stmt.where(Service.category_id == category_id)

    stmt = stmt.order_by(Service.sort_order.asc(), Service.name.asc())
    stmt = stmt.options(selectinload(Service.owner), selectinload(Service.support_group), selectinload(Service.category))
    result = await db.execute(stmt)
    services = result.scalars().all()

    # Count workflows per service
    svc_ids = [s.id for s in services]
    if svc_ids:
        count_stmt = select(Workflow.service_id, func.count(Workflow.id)).where(
            Workflow.service_id.in_(svc_ids), Workflow.is_published == True, Workflow.is_active == True
        ).group_by(Workflow.service_id)
        count_result = await db.execute(count_stmt)
        counts = {row[0]: row[1] for row in count_result.all()}
    else:
        counts = {}

    return [_service_to_dict(s, counts.get(s.id, 0)) for s in services]


@router.get("/services/{service_id}")
async def get_service(
    service_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get service detail with linked workflows."""
    stmt = (
        select(Service)
        .where(Service.id == service_id)
        .options(
            selectinload(Service.owner),
            selectinload(Service.support_group),
            selectinload(Service.category),
            selectinload(Service.workflows).selectinload(Workflow.allowed_groups),
        )
    )
    result = await db.execute(stmt)
    svc = result.scalar_one_or_none()
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")

    # For non-admins, only show active services
    if not svc.is_active and current_user.role != "admin":
        raise HTTPException(status_code=404, detail="Service not found")

    # Filter published workflows; apply group permissions for non-admin/dev users
    workflows = svc.workflows or []
    if current_user.role not in ("admin", "developer"):
        user_group_ids = {g.id for g in current_user.groups}
        workflows = [
            w for w in workflows
            if w.is_published and w.is_active and user_group_ids & {g.id for g in (w.allowed_groups or [])}
        ]
    else:
        workflows = [w for w in workflows if w.is_published and w.is_active]

    wf_list = []
    for w in workflows:
        # Count steps
        step_count_stmt = select(func.count(WorkflowStep.id)).where(WorkflowStep.workflow_id == w.id)
        step_result = await db.execute(step_count_stmt)
        step_count = step_result.scalar() or 0

        run_count_stmt = select(func.count(WorkflowRun.id)).where(WorkflowRun.workflow_id == w.id)
        run_result = await db.execute(run_count_stmt)
        run_count = run_result.scalar() or 0

        wf_list.append({
            "id": w.id,
            "name": w.name,
            "description": w.description or "",
            "portal_icon": w.portal_icon or "",
            "steps_count": step_count,
            "runs_count": run_count,
        })

    return {
        **_service_to_dict(svc, len(wf_list)),
        "workflows": wf_list,
    }


@router.post("/services")
async def create_service(
    data: ServiceCreate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a new service (admin only)."""
    key = data.key or _slugify(data.name)

    existing = await db.execute(
        select(Service).where((Service.name == data.name) | (Service.key == key))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Service with this name or key already exists")

    # Validate category
    if data.category_id is not None:
        cat_stmt = select(Category).where(Category.id == data.category_id)
        cat_result = await db.execute(cat_stmt)
        if not cat_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Category not found")

    # Validate owner
    if data.owner_id is not None:
        user_stmt = select(User).where(User.id == data.owner_id)
        user_result = await db.execute(user_stmt)
        if not user_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Owner user not found")

    # Validate support group
    if data.support_group_id is not None:
        grp_stmt = select(Group).where(Group.id == data.support_group_id)
        grp_result = await db.execute(grp_stmt)
        if not grp_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Support group not found")

    svc = Service(
        name=data.name,
        key=key,
        description=data.description or "",
        icon=data.icon or "",
        category_id=data.category_id,
        owner_id=data.owner_id,
        support_group_id=data.support_group_id,
        sort_order=data.sort_order,
        custom_data=data.custom_data or {},
    )
    db.add(svc)
    await db.commit()
    await db.refresh(svc)

    # Reload with relationships
    stmt = select(Service).where(Service.id == svc.id).options(
        selectinload(Service.owner), selectinload(Service.support_group), selectinload(Service.category)
    )
    result = await db.execute(stmt)
    return _service_to_dict(result.scalar_one())


@router.put("/services/{service_id}")
async def update_service(
    service_id: int,
    data: ServiceUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update a service (admin only)."""
    stmt = select(Service).where(Service.id == service_id).options(
        selectinload(Service.owner), selectinload(Service.support_group), selectinload(Service.category)
    )
    result = await db.execute(stmt)
    svc = result.scalar_one_or_none()
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")

    if data.name is not None and data.name != svc.name:
        existing = await db.execute(select(Service).where(Service.name == data.name, Service.id != service_id))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Service with this name already exists")
        svc.name = data.name

    if data.key is not None and data.key != svc.key:
        existing = await db.execute(select(Service).where(Service.key == data.key, Service.id != service_id))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Service with this key already exists")
        svc.key = data.key

    if data.description is not None:
        svc.description = data.description
    if data.icon is not None:
        svc.icon = data.icon
    if data.category_id is not None:
        cat_stmt = select(Category).where(Category.id == data.category_id)
        cat_result = await db.execute(cat_stmt)
        if not cat_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Category not found")
        svc.category_id = data.category_id
    elif data.category_id is None and "category_id" in data.model_fields_set:
        svc.category_id = None
    if data.owner_id is not None:
        user_stmt = select(User).where(User.id == data.owner_id)
        user_result = await db.execute(user_stmt)
        if not user_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Owner user not found")
        svc.owner_id = data.owner_id
    elif data.owner_id is None and "owner_id" in data.model_fields_set:
        svc.owner_id = None
    if data.support_group_id is not None:
        grp_stmt = select(Group).where(Group.id == data.support_group_id)
        grp_result = await db.execute(grp_stmt)
        if not grp_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Support group not found")
        svc.support_group_id = data.support_group_id
    elif data.support_group_id is None and "support_group_id" in data.model_fields_set:
        svc.support_group_id = None
    if data.is_active is not None:
        if not data.is_active:
            # Warn if workflows reference this service
            wf_stmt = select(func.count(Workflow.id)).where(Workflow.service_id == service_id)
            wf_result = await db.execute(wf_stmt)
            wf_count = wf_result.scalar() or 0
            if wf_count > 0:
                pass  # Still allow, but frontend can show warning
        svc.is_active = data.is_active
    if data.sort_order is not None:
        svc.sort_order = data.sort_order
    if data.custom_data is not None:
        svc.custom_data = data.custom_data

    await db.commit()
    await db.refresh(svc)

    stmt = select(Service).where(Service.id == svc.id).options(
        selectinload(Service.owner), selectinload(Service.support_group), selectinload(Service.category)
    )
    result = await db.execute(stmt)
    return _service_to_dict(result.scalar_one())


@router.delete("/services/{service_id}")
async def delete_service(
    service_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Deactivate a service (soft-delete). Warns if workflows reference it."""
    stmt = select(Service).where(Service.id == service_id)
    result = await db.execute(stmt)
    svc = result.scalar_one_or_none()
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")

    wf_stmt = select(func.count(Workflow.id)).where(Workflow.service_id == service_id)
    wf_result = await db.execute(wf_stmt)
    wf_count = wf_result.scalar() or 0

    svc.is_active = False
    await db.commit()

    return {
        "message": "Service deactivated",
        "linked_workflows": wf_count,
        "warning": f"This service has {wf_count} linked workflow(s). They will be unassigned." if wf_count > 0 else None,
    }

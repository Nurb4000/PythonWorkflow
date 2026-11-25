"""
D2: Unified search across workflows, forms, field defs, CI types/items.

Single endpoint returning grouped results. Server-side, uses ILIKE for
PostgreSQL text search.
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from typing import List, Dict, Any

from app.core.database import get_db
from app.models.auth import User
from app.api.auth import get_current_user

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/")
async def unified_search(
    q: str = Query(..., min_length=1, max_length=100, description="Search query"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Search across all major objects. Returns grouped results.

    Results are scoped to the caller's permissions (findings #28): workflows are
    filtered to the caller's groups (admin/developer see all), forms are filtered
    to published+active for non-power users, and shared reference data (field
    definitions, CI types, CI items) is limited to active rows.
    """
    from app.models.auth import workflow_permissions

    pattern = f"%{q}%"
    is_power_user = current_user.role in ("admin", "developer")
    user_group_ids = [g.id for g in (current_user.groups or [])]

    results = {
        "workflows": [],
        "forms": [],
        "field_definitions": [],
        "ci_types": [],
        "ci_items": [],
    }

    # Search workflows (name, description). Power users see all; others only see
    # workflows whose allowed_groups intersect the caller's groups.
    from app.models.schemas import Workflow
    wf_conditions = [or_(Workflow.name.ilike(pattern), Workflow.description.ilike(pattern))]
    if not is_power_user:
        wf_conditions.append(and_(
            workflow_permissions.c.workflow_id == Workflow.id,
            workflow_permissions.c.group_id.in_(user_group_ids),
        ))
    wf_query = select(Workflow).where(and_(*wf_conditions)).limit(page_size)
    wf_result = await db.execute(wf_query)
    workflows = wf_result.scalars().all()
    results["workflows"] = [
        {"id": w.id, "name": w.name, "description": w.description, "type": "workflow"}
        for w in workflows
    ]

    # Search forms (name, description). Non-power users only see published+active.
    from app.models.forms import Form
    form_conditions = [Form.is_active == True]
    if not is_power_user:
        form_conditions.append(Form.is_published == True)
    form_conditions.append(or_(Form.name.ilike(pattern), Form.description.ilike(pattern)))
    form_query = select(Form).where(and_(*form_conditions)).limit(page_size)
    form_result = await db.execute(form_query)
    forms = form_result.scalars().all()
    results["forms"] = [
        {"id": f.id, "name": f.name, "description": f.description, "type": "form"}
        for f in forms
    ]

    # Search field definitions (key, label, description). Shared reference data:
    # active rows only for every role.
    from app.models.field_library import FieldDefinition
    field_conditions = [
        FieldDefinition.is_active == True,
        or_(
            FieldDefinition.key.ilike(pattern),
            FieldDefinition.label.ilike(pattern),
            FieldDefinition.description.ilike(pattern)
        ),
    ]
    field_query = select(FieldDefinition).where(and_(*field_conditions)).limit(page_size)
    field_result = await db.execute(field_query)
    fields = field_result.scalars().all()
    results["field_definitions"] = [
        {"id": f.id, "key": f.key, "label": f.label, "field_type": f.field_type}
        for f in fields
    ]

    # Search CI types (name, description). Shared reference data: active only.
    from app.models.cmdb import CIType
    ci_type_conditions = [
        CIType.is_active == True,
        or_(
            CIType.name.ilike(pattern),
            CIType.description.ilike(pattern)
        ),
    ]
    ci_type_query = select(CIType).where(and_(*ci_type_conditions)).limit(page_size)
    ci_type_result = await db.execute(ci_type_query)
    ci_types = ci_type_result.scalars().all()
    results["ci_types"] = [
        {"id": c.id, "name": c.name, "description": c.description}
        for c in ci_types
    ]

    # Search CI items (name). Active only.
    from app.models.cmdb import ConfigurationItem
    ci_conditions = [
        ConfigurationItem.is_active == True,
        ConfigurationItem.name.ilike(pattern),
    ]
    ci_query = select(ConfigurationItem).where(and_(*ci_conditions)).limit(page_size)
    ci_result = await db.execute(ci_query)
    cis = ci_result.scalars().all()
    results["ci_items"] = [
        {"id": c.id, "name": c.name}
        for c in cis
    ]

    # Compute totals for each type (same scoping as the queries above).
    totals = {}
    wf_total = select(func.count()).select_from(Workflow).where(and_(*wf_conditions))
    totals[Workflow.__tablename__] = (await db.execute(wf_total)).scalar() or 0

    form_total = select(func.count()).select_from(Form).where(and_(*form_conditions))
    totals[Form.__tablename__] = (await db.execute(form_total)).scalar() or 0

    field_total = select(func.count()).select_from(FieldDefinition).where(and_(*field_conditions))
    totals[FieldDefinition.__tablename__] = (await db.execute(field_total)).scalar() or 0

    ci_type_total = select(func.count()).select_from(CIType).where(and_(*ci_type_conditions))
    totals[CIType.__tablename__] = (await db.execute(ci_type_total)).scalar() or 0

    ci_total = select(func.count()).select_from(ConfigurationItem).where(and_(*ci_conditions))
    totals[ConfigurationItem.__tablename__] = (await db.execute(ci_total)).scalar() or 0

    return {
        "query": q,
        "results": results,
        "totals": totals,
        "page": page,
        "page_size": page_size
    }

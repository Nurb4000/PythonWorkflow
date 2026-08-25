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
    """Search across all major objects. Returns grouped results."""
    pattern = f"%{q}%"
    
    results = {
        "workflows": [],
        "forms": [],
        "field_definitions": [],
        "ci_types": [],
        "ci_items": [],
    }
    
    # Search workflows (name, description)
    from app.models.schemas import Workflow
    wf_query = select(Workflow).where(
        or_(
            Workflow.name.ilike(pattern),
            Workflow.description.ilike(pattern)
        )
    ).limit(page_size)
    wf_result = await db.execute(wf_query)
    workflows = wf_result.scalars().all()
    results["workflows"] = [
        {"id": w.id, "name": w.name, "description": w.description, "type": "workflow"}
        for w in workflows
    ]
    
    # Search forms (name, description)
    from app.models.forms import Form
    form_query = select(Form).where(
        or_(
            Form.name.ilike(pattern),
            Form.description.ilike(pattern)
        )
    ).limit(page_size)
    form_result = await db.execute(form_query)
    forms = form_result.scalars().all()
    results["forms"] = [
        {"id": f.id, "name": f.name, "description": f.description, "type": "form"}
        for f in forms
    ]
    
    # Search field definitions (key, label, description)
    from app.models.field_library import FieldDefinition
    field_query = select(FieldDefinition).where(
        and_(
            or_(
                FieldDefinition.key.ilike(pattern),
                FieldDefinition.label.ilike(pattern),
                FieldDefinition.description.ilike(pattern)
            ),
            FieldDefinition.is_active == True
        )
    ).limit(page_size)
    field_result = await db.execute(field_query)
    fields = field_result.scalars().all()
    results["field_definitions"] = [
        {"id": f.id, "key": f.key, "label": f.label, "field_type": f.field_type}
        for f in fields
    ]
    
    # Search CI types (name, description)
    from app.models.cmdb import CIType
    ci_type_query = select(CIType).where(
        and_(
            or_(
                CIType.name.ilike(pattern),
                CIType.description.ilike(pattern)
            ),
            CIType.is_active == True
        )
    ).limit(page_size)
    ci_type_result = await db.execute(ci_type_query)
    ci_types = ci_type_result.scalars().all()
    results["ci_types"] = [
        {"id": c.id, "name": c.name, "description": c.description}
        for c in ci_types
    ]
    
    # Search CI items (name)
    from app.models.cmdb import ConfigurationItem
    ci_query = select(ConfigurationItem).where(
        and_(
            ConfigurationItem.name.ilike(pattern),
            ConfigurationItem.is_active == True
        )
    ).limit(page_size)
    ci_result = await db.execute(ci_query)
    cis = ci_result.scalars().all()
    results["ci_items"] = [
        {"id": c.id, "name": c.name}
        for c in cis
    ]
    
    # Compute totals for each type
    totals = {}
    for model, conditions in [
        (Workflow, [or_(Workflow.name.ilike(pattern), Workflow.description.ilike(pattern))]),
        (Form, [or_(Form.name.ilike(pattern), Form.description.ilike(pattern))]),
        (FieldDefinition, [or_(FieldDefinition.key.ilike(pattern), FieldDefinition.label.ilike(pattern), FieldDefinition.description.ilike(pattern)), FieldDefinition.is_active == True]),
        (CIType, [or_(CIType.name.ilike(pattern), CIType.description.ilike(pattern)), CIType.is_active == True]),
        (ConfigurationItem, [ConfigurationItem.name.ilike(pattern), ConfigurationItem.is_active == True]),
    ]:
        count_stmt = select(func.count()).select_from(model).where(*conditions)
        total_result = await db.execute(count_stmt)
        totals[model.__tablename__] = total_result.scalar() or 0
    
    return {
        "query": q,
        "results": results,
        "totals": totals,
        "page": page,
        "page_size": page_size
    }

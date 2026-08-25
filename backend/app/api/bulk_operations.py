"""
E2: Bulk operations for workflows, forms, CI types.

Multi-select tag/reassign-owner/move/deactivate in list views.
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import List, Optional

from app.core.database import get_db
from app.models.auth import User
from app.api.auth import get_current_admin
from app.models.schemas import Workflow
from app.models.forms import Form
from app.models.cmdb import CIType

router = APIRouter(prefix="/bulk", tags=["bulk-operations"])


@router.post("/workflows/deprecate")
async def bulk_deprecate_workflows(
    workflow_ids: List[int] = Body(...),
    suggested_replacement_id: Optional[int] = None,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Deprecate multiple workflows."""
    stmt = update(Workflow).where(Workflow.id.in_(workflow_ids)).values(
        is_deprecated=True,
        deprecated_by_id=current_user.id
    )
    if suggested_replacement_id:
        stmt = stmt.values(suggested_replacement_id=suggested_replacement_id)
    
    await db.execute(stmt)
    await db.commit()
    
    return {"deprecated": len(workflow_ids), "workflow_ids": workflow_ids}


@router.post("/workflows/reactivate")
async def bulk_reactivate_workflows(
    workflow_ids: List[int] = Body(...),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Reactivate multiple workflows."""
    stmt = update(Workflow).where(Workflow.id.in_(workflow_ids)).values(
        is_deprecated=False,
        deprecated_at=None,
        deprecated_by_id=None,
        suggested_replacement_id=None
    )
    await db.execute(stmt)
    await db.commit()
    
    return {"reactivated": len(workflow_ids), "workflow_ids": workflow_ids}


@router.post("/workflows/reassign-owner")
async def bulk_reassign_owner(
    workflow_ids: List[int] = Body(...),
    new_owner_id: int = Body(...),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Reassign ownership of multiple workflows."""
    stmt = update(Workflow).where(Workflow.id.in_(workflow_ids)).values(
        owner_user_id=new_owner_id
    )
    await db.execute(stmt)
    await db.commit()
    
    return {"reassigned": len(workflow_ids), "new_owner_id": new_owner_id}


@router.post("/forms/deprecate")
async def bulk_deprecate_forms(
    form_ids: List[int] = Body(...),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Deprecate multiple forms."""
    stmt = update(Form).where(Form.id.in_(form_ids)).values(
        is_deprecated=True,
        deprecated_by_id=current_user.id
    )
    await db.execute(stmt)
    await db.commit()
    
    return {"deprecated": len(form_ids), "form_ids": form_ids}


@router.post("/forms/reactivate")
async def bulk_reactivate_forms(
    form_ids: List[int] = Body(...),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Reactivate multiple forms."""
    stmt = update(Form).where(Form.id.in_(form_ids)).values(
        is_deprecated=False,
        deprecated_at=None,
        deprecated_by_id=None
    )
    await db.execute(stmt)
    await db.commit()
    
    return {"reactivated": len(form_ids), "form_ids": form_ids}


@router.post("/ci-types/deprecate")
async def bulk_deprecate_ci_types(
    ci_type_ids: List[int] = Body(...),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Deprecate multiple CI types (sets is_active=False)."""
    stmt = update(CIType).where(CIType.id.in_(ci_type_ids)).values(
        is_active=False
    )
    await db.execute(stmt)
    await db.commit()
    
    return {"deactivated": len(ci_type_ids), "ci_type_ids": ci_type_ids}


@router.post("/ci-types/reactivate")
async def bulk_reactivate_ci_types(
    ci_type_ids: List[int] = Body(...),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Reactivate multiple CI types (sets is_active=True)."""
    stmt = update(CIType).where(CIType.id.in_(ci_type_ids)).values(
        is_active=True
    )
    await db.execute(stmt)
    await db.commit()
    
    return {"reactivated": len(ci_type_ids), "ci_type_ids": ci_type_ids}

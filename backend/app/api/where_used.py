"""
Where-used API endpoints — scan for field definition references.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.auth import User
from app.api.auth import get_current_admin
from app.services.where_used_service import where_used_service

router = APIRouter(prefix="/admin/where-used", tags=["where-used"])


@router.get("/field/{field_id}")
async def get_field_where_used(
    field_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get all references to a field definition (admin only)."""
    result = await where_used_service.find_all_references(db, field_id)
    return result


@router.get("/forms/{field_key}")
async def get_form_references(
    field_key: str,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get all forms referencing a field key (admin only)."""
    references = await where_used_service.find_form_references(db, field_key)
    return {"field_key": field_key, "references": references}


@router.get("/ci-types/{field_key}")
async def get_ci_type_references(
    field_key: str,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get all CI types referencing a field key (admin only)."""
    references = await where_used_service.find_ci_type_references(db, field_key)
    return {"field_key": field_key, "references": references}

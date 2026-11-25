"""
Lookup API endpoints for form fields.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.models.auth import User
from app.api.auth import get_current_user
from app.services.lookup_service import lookup_service

router = APIRouter(prefix="/lookup", tags=["lookup"])

# Roles permitted to use the free lookup directory endpoints. Matches the permission
# model used for task operations (tasks.py) and implements findings #29: regular
# portal users must not be able to enumerate the full user/CI directory (incl. role).
LOOKUP_ROLE_ALLOWLIST = ("admin", "developer", "staff")


def _require_lookup_role(current_user: User) -> None:
    """Raise 403 unless the caller has a role that may use the free lookup endpoints.

    Applied at the endpoint layer only, so the internal form-resolution path
    (forms.py -> lookup_service.perform_lookup -> lookup_users/lookup_ci_items) stays
    available to every authenticated role.
    """
    if current_user.role not in LOOKUP_ROLE_ALLOWLIST:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Role '{current_user.role}' is not permitted to use the lookup directory"
            ),
        )


@router.get("/users")
async def search_users(
    q: str = Query(..., description="Search query"),
    field: str = Query("username", description="Field to search (username, email, full_name)"),
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Search users for lookup fields."""
    _require_lookup_role(current_user)
    results = await lookup_service.lookup_users(db, field, q, limit)
    return {"results": results}


@router.get("/ci-items")
async def search_ci_items(
    q: str = Query(..., description="Search query"),
    type_key: str = Query(..., description="CI type key"),
    field: str = Query("name", description="Field to search in ci_data"),
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Search CI items for lookup fields."""
    _require_lookup_role(current_user)
    results = await lookup_service.lookup_ci_items(db, type_key, field, q, limit)
    return {"results": results}


@router.post("/perform")
async def perform_lookup(
    lookup_config: dict = Body(...),
    search_value: str = Body(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Perform a lookup and return result."""
    _require_lookup_role(current_user)
    result = await lookup_service.perform_lookup(db, lookup_config, search_value)
    if not result:
        raise HTTPException(status_code=404, detail="No results found")
    
    # Extract configured result fields
    result_fields = lookup_config.get('result_fields', [])
    if result_fields:
        extracted = await lookup_service.extract_result_fields(result, result_fields)
        result['extracted_fields'] = extracted
    
    return result

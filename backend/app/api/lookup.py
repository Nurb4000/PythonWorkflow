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


@router.get("/users")
async def search_users(
    q: str = Query(..., description="Search query"),
    field: str = Query("username", description="Field to search (username, email, full_name)"),
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Search users for lookup fields."""
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
    result = await lookup_service.perform_lookup(db, lookup_config, search_value)
    if not result:
        raise HTTPException(status_code=404, detail="No results found")
    
    # Extract configured result fields
    result_fields = lookup_config.get('result_fields', [])
    if result_fields:
        extracted = await lookup_service.extract_result_fields(result, result_fields)
        result['extracted_fields'] = extracted
    
    return result

"""
Audit trail API — view change history for all objects.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.auth import User
from app.api.auth import get_current_user
from app.services.audit_service import audit_service

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/{entity_type}/{entity_id}")
async def get_entity_audit_trail(
    entity_type: str,
    entity_id: int,
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get audit trail for a specific entity."""
    entries = await audit_service.get_audit_trail(
        db, entity_type, entity_id, limit=limit
    )
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "entries": [e.to_dict() for e in entries],
        "total": len(entries)
    }


@router.get("/user/{user_id}")
async def get_user_audit_trail(
    user_id: int,
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get audit trail for a specific user's actions."""
    entries = await audit_service.get_audit_trail(
        db, None, None, user_id=user_id, limit=limit
    )
    return {
        "user_id": user_id,
        "entries": [e.to_dict() for e in entries],
        "total": len(entries)
    }

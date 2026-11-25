from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List

from app.core.database import get_db
from app.models.auth import User
from app.models.sql_views import SQLView
from app.services.sql_view_service import sql_view_service
from app.api.auth import get_current_developer

router = APIRouter()


def _view_to_dict(view: SQLView) -> dict:
    return {
        "id": view.id,
        "name": view.name,
        "description": view.description,
        "definition_sql": view.definition_sql,
        "is_active": view.is_active,
        "created_by": view.created_by,
        "created_at": view.created_at.isoformat() if view.created_at else None,
        "updated_at": view.updated_at.isoformat() if view.updated_at else None,
    }


@router.get("/")
async def list_views(
    include_inactive: bool = Query(False),
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """List all SQL views. By default excludes deactivated views."""
    try:
        views = await sql_view_service.list_views(db, include_inactive=include_inactive)
        return [_view_to_dict(v) for v in views]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/")
async def create_view(
    name: str,
    definition_sql: str,
    description: Optional[str] = "",
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """Create a new SQL view."""
    try:
        view = await sql_view_service.create_view(
            db, name, definition_sql, description, current_user.id
        )
        return _view_to_dict(view)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{view_id}")
async def update_view(
    view_id: int,
    definition_sql: Optional[str] = None,
    description: Optional[str] = None,
    is_active: Optional[bool] = None,
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing SQL view."""
    try:
        view = await sql_view_service.update_view(
            db, view_id, definition_sql, description, is_active
        )
        return _view_to_dict(view)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{view_id}")
async def delete_view(
    view_id: int,
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a SQL view (drops from database but keeps record)."""
    try:
        success = await sql_view_service.delete_view(db, view_id)
        if not success:
            raise HTTPException(status_code=404, detail="View not found")
        return {"message": "View deactivated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

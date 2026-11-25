"""
Role permissions API — manage table/field access per role.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional

from app.core.database import get_db
from app.models.auth import User
from app.api.auth import get_current_admin, get_current_user
from app.models.role_permissions import RolePermission, role_permission_service

router = APIRouter(prefix="/admin/role-permissions", tags=["role-permissions"])


@router.get("/")
async def list_permissions(
    role_id: Optional[int] = Query(None),
    table_name: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """List role permissions (admin only)."""
    stmt = select(RolePermission)
    
    if role_id:
        stmt = stmt.where(RolePermission.role_id == role_id)
    if table_name:
        stmt = stmt.where(RolePermission.table_name == table_name)
    
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0
    
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size).order_by(RolePermission.table_name, RolePermission.role_id)
    
    result = await db.execute(stmt)
    permissions = result.scalars().all()
    
    return {
        "items": [p.to_dict() for p in permissions],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total else 0
    }


@router.post("/")
async def create_permission(
    data: dict,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a role permission (admin only)."""
    role_id = data.get("role_id")
    table_name = data.get("table_name")
    
    if not role_id or not table_name:
        raise HTTPException(status_code=400, detail="role_id and table_name are required")
    
    # Check if permission already exists
    stmt = select(RolePermission).where(
        RolePermission.role_id == role_id,
        RolePermission.table_name == table_name
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Permission already exists for this role/table")
    
    permission = RolePermission(
        role_id=role_id,
        table_name=table_name,
        can_view=data.get("can_view", True),
        can_edit=data.get("can_edit", False),
        can_delete=data.get("can_delete", False),
        visible_fields=data.get("visible_fields", []),
        editable_fields=data.get("editable_fields", []),
        is_active=data.get("is_active", True)
    )
    
    db.add(permission)
    await db.commit()
    await db.refresh(permission)
    
    return {"id": permission.id, "message": "Permission created"}


@router.put("/{permission_id}")
async def update_permission(
    permission_id: int,
    data: dict,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update a role permission (admin only)."""
    stmt = select(RolePermission).where(RolePermission.id == permission_id)
    result = await db.execute(stmt)
    permission = result.scalar_one_or_none()
    
    if not permission:
        raise HTTPException(status_code=404, detail="Permission not found")
    
    # Update fields
    for field in ["role_id", "table_name", "can_view", "can_edit", "can_delete", 
                  "visible_fields", "editable_fields", "is_active"]:
        if field in data:
            setattr(permission, field, data[field])
    
    await db.commit()
    await db.refresh(permission)
    
    return {"message": "Permission updated", "id": permission.id}


@router.delete("/{permission_id}")
async def delete_permission(
    permission_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a role permission (admin only)."""
    stmt = select(RolePermission).where(RolePermission.id == permission_id)
    result = await db.execute(stmt)
    permission = result.scalar_one_or_none()
    
    if not permission:
        raise HTTPException(status_code=404, detail="Permission not found")
    
    await db.delete(permission)
    await db.commit()
    
    return {"message": "Permission deleted"}


@router.get("/check/{table_name}")
async def check_access(
    table_name: str,
    action: str = Query("view", description="view, edit, or delete"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Check if current user has access to a table (any role)."""
    can_access = await role_permission_service.can_user_access_table(
        db, current_user, table_name, action
    )
    
    if not can_access:
        raise HTTPException(status_code=403, detail=f"Access denied: cannot {action} {table_name}")
    
    return {"access": True, "table": table_name, "action": action}


@router.get("/visible-fields/{table_name}")
async def get_visible_fields(
    table_name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get fields visible to current user for a table."""
    fields = await role_permission_service.get_visible_fields(db, current_user, table_name)
    return {"table": table_name, "fields": fields}


@router.get("/editable-fields/{table_name}")
async def get_editable_fields(
    table_name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get fields editable by current user for a table."""
    fields = await role_permission_service.get_editable_fields(db, current_user, table_name)
    return {"table": table_name, "fields": fields}

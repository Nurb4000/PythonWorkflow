"""
Admin role management API — CRUD for custom roles.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional

from app.core.database import get_db
from app.models.auth import User
from app.api.auth import get_current_admin
from app.models.roles import CustomRole

router = APIRouter(prefix="/admin/roles", tags=["roles"])


@router.get("/")
async def list_roles(
    is_active: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """List custom roles (admin only)."""
    stmt = select(CustomRole)
    if is_active is not None:
        stmt = stmt.where(CustomRole.is_active == is_active)
    
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0
    
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size).order_by(CustomRole.name)
    
    result = await db.execute(stmt)
    roles = result.scalars().all()
    
    return {
        "items": [r.to_dict() for r in roles],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total else 0
    }


@router.get("/{role_id}")
async def get_role(
    role_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get a single custom role (admin only)."""
    stmt = select(CustomRole).where(CustomRole.id == role_id)
    result = await db.execute(stmt)
    role = result.scalar_one_or_none()
    
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    return role.to_dict()


@router.post("/", status_code=201)
async def create_role(
    data: dict,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a new custom role (admin only)."""
    name = data.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    
    # Check for duplicate name
    stmt = select(CustomRole.id).where(CustomRole.name == name)
    result = await db.execute(stmt)
    if result.scalar() is not None:
        raise HTTPException(status_code=409, detail=f"Role '{name}' already exists")
    
    role = CustomRole(
        name=name,
        description=data.get("description", ""),
        permissions=data.get("permissions", []),
        is_active=data.get("is_active", True)
    )
    
    db.add(role)
    await db.commit()
    await db.refresh(role)
    
    return {"id": role.id, "name": role.name, "message": "Role created"}


@router.put("/{role_id}")
async def update_role(
    role_id: int,
    data: dict,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update a custom role (admin only)."""
    stmt = select(CustomRole).where(CustomRole.id == role_id)
    result = await db.execute(stmt)
    role = result.scalar_one_or_none()
    
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    # Update fields
    for field in ["name", "description", "permissions", "is_active"]:
        if field in data:
            setattr(role, field, data[field])
    
    await db.commit()
    await db.refresh(role)
    
    return {"message": "Role updated", "id": role.id}


@router.delete("/{role_id}")
async def delete_role(
    role_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a custom role (admin only)."""
    stmt = select(CustomRole).where(CustomRole.id == role_id)
    result = await db.execute(stmt)
    role = result.scalar_one_or_none()
    
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    # Check if role is in use by any users
    from app.models.auth import User
    user_stmt = select(func.count()).select_from(User).where(
        User.roles.astext.contains(f'"{role.name}"')
    )
    user_result = await db.execute(user_stmt)
    if user_result.scalar() > 0:
        raise HTTPException(status_code=409, detail=f"Role '{role.name}' is assigned to users. Reassign users first.")
    
    await db.delete(role)
    await db.commit()
    
    return {"message": "Role deleted"}

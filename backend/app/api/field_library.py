"""
C1: Field Library API — CRUD for shared field definitions.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from typing import List, Optional

from app.core.database import get_db
from app.models.field_library import FieldDefinition
from app.models.auth import User
from app.api.auth import get_current_admin, get_current_developer

router = APIRouter(prefix="/field-library", tags=["field-library"])


@router.get("/")
async def list_field_definitions(
    search: Optional[str] = Query(None),
    field_type: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db)
):
    """List field definitions (C1)."""
    stmt = select(FieldDefinition)
    
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(or_(
            FieldDefinition.key.ilike(pattern),
            FieldDefinition.label.ilike(pattern),
            FieldDefinition.description.ilike(pattern)
        ))
    
    if field_type:
        stmt = stmt.where(FieldDefinition.field_type == field_type)
    
    if is_active is not None:
        stmt = stmt.where(FieldDefinition.is_active == is_active)
    
    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0
    
    # Paginate
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size).order_by(FieldDefinition.label)
    
    result = await db.execute(stmt)
    fields = result.scalars().all()
    
    return {
        "items": [
            {
                "id": f.id,
                "key": f.key,
                "label": f.label,
                "description": f.description,
                "field_type": f.field_type,
                "options": f.options or [],
                "validation_rules": f.validation_rules or {},
                "help_text": f.help_text,
                "is_active": f.is_active,
                "is_deprecated": f.is_deprecated,
                "owner_user_id": f.owner_user_id,
                "tags": f.tags or [],
                "created_at": f.created_at.isoformat() if f.created_at else None,
                "updated_at": f.updated_at.isoformat() if f.updated_at else None,
            }
            for f in fields
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total else 0
    }


@router.get("/{field_id}")
async def get_field_definition(
    field_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a single field definition."""
    stmt = select(FieldDefinition).where(FieldDefinition.id == field_id)
    result = await db.execute(stmt)
    field = result.scalar_one_or_none()
    
    if not field:
        raise HTTPException(status_code=404, detail="Field definition not found")
    
    return {
        "id": field.id,
        "key": field.key,
        "label": field.label,
        "description": field.description,
        "field_type": field.field_type,
        "options": field.options or [],
        "validation_rules": field.validation_rules or {},
        "help_text": field.help_text,
        "is_active": field.is_active,
        "is_deprecated": field.is_deprecated,
        "owner_user_id": field.owner_user_id,
        "tags": field.tags or [],
        "created_at": field.created_at.isoformat() if field.created_at else None,
        "updated_at": field.updated_at.isoformat() if field.updated_at else None,
    }


@router.post("/", status_code=201)
async def create_field_definition(
    data: dict,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a new field definition (admin only)."""
    # Validate required fields
    key = data.get("key")
    label = data.get("label")
    field_type = data.get("field_type", "string")
    
    if not key or not label:
        raise HTTPException(status_code=400, detail="key and label are required")
    
    # Check for duplicate key
    stmt = select(FieldDefinition.id).where(FieldDefinition.key == key)
    result = await db.execute(stmt)
    if result.scalar() is not None:
        raise HTTPException(status_code=409, detail=f"Field definition with key '{key}' already exists")
    
    field = FieldDefinition(
        key=key,
        label=label,
        description=data.get("description", ""),
        field_type=field_type,
        options=data.get("options", []),
        validation_rules=data.get("validation_rules", {}),
        help_text=data.get("help_text", ""),
        owner_user_id=current_user.id,
        tags=data.get("tags", []),
        is_active=data.get("is_active", True)
    )
    
    db.add(field)
    await db.commit()
    await db.refresh(field)
    
    return {
        "id": field.id,
        "key": field.key,
        "label": field.label,
        "message": "Field definition created"
    }


@router.put("/{field_id}")
async def update_field_definition(
    field_id: int,
    data: dict,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update a field definition (admin only)."""
    stmt = select(FieldDefinition).where(FieldDefinition.id == field_id)
    result = await db.execute(stmt)
    field = result.scalar_one_or_none()
    
    if not field:
        raise HTTPException(status_code=404, detail="Field definition not found")
    
    # Update fields
    for update_field in ["label", "description", "field_type", "options", "validation_rules", 
                         "help_text", "tags", "is_active"]:
        if update_field in data:
            setattr(field, update_field, data[update_field])
    
    if "key" in data and data["key"] != field.key:
        # Check new key uniqueness
        stmt_check = select(FieldDefinition.id).where(
            and_(FieldDefinition.key == data["key"], FieldDefinition.id != field_id)
        )
        result_check = await db.execute(stmt_check)
        if result_check.scalar() is not None:
            raise HTTPException(status_code=409, detail=f"Field definition with key '{data['key']}' already exists")
        field.key = data["key"]
    
    await db.commit()
    await db.refresh(field)
    
    return {"message": "Field definition updated", "id": field.id}


@router.post("/{field_id}/deprecate")
async def deprecate_field_definition(
    field_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Deprecate a field definition."""
    stmt = select(FieldDefinition).where(FieldDefinition.id == field_id)
    result = await db.execute(stmt)
    field = result.scalar_one_or_none()
    
    if not field:
        raise HTTPException(status_code=404, detail="Field definition not found")
    
    field.is_deprecated = True
    field.deprecated_at = func.now()
    field.deprecated_by_id = current_user.id
    field.is_active = False
    
    await db.commit()
    
    return {"message": "Field definition deprecated", "id": field.id}


@router.delete("/{field_id}")
async def delete_field_definition(
    field_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a field definition (admin only, hard delete)."""
    stmt = select(FieldDefinition).where(FieldDefinition.id == field_id)
    result = await db.execute(stmt)
    field = result.scalar_one_or_none()
    
    if not field:
        raise HTTPException(status_code=404, detail="Field definition not found")
    
    await db.delete(field)
    await db.commit()
    
    return {"message": "Field definition deleted"}


@router.get("/{field_id}/where-used")
async def get_field_where_used(
    field_id: int,
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db)
):
    """C5: Show where a field definition is used (forms, CI types)."""
    stmt = select(FieldDefinition).where(FieldDefinition.id == field_id)
    result = await db.execute(stmt)
    field = result.scalar_one_or_none()

    if not field:
        raise HTTPException(status_code=404, detail="Field definition not found")

    from app.services.where_used_service import where_used_service
    return await where_used_service.find_all_references(db, field_id)


@router.get("/scan/forms")
async def scan_forms_for_migration(
    min_uses: int = Query(2, ge=1, le=10),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Scan forms for fields that could be promoted to library (admin only)."""
    from app.services.field_library_migration import field_library_migration_service
    candidates = await field_library_migration_service.scan_forms(db, min_uses)
    return {"candidates": candidates, "total": len(candidates)}


@router.get("/scan/ci-types")
async def scan_ci_types_for_migration(
    min_uses: int = Query(2, ge=1, le=10),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Scan CI types for fields that could be promoted to library (admin only)."""
    from app.services.field_library_migration import field_library_migration_service
    candidates = await field_library_migration_service.scan_ci_types(db, min_uses)
    return {"candidates": candidates, "total": len(candidates)}


@router.get("/migration-plan")
async def get_migration_plan(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Generate full migration plan (admin only)."""
    from app.services.field_library_migration import field_library_migration_service
    
    forms_candidates = await field_library_migration_service.scan_forms(db, min_uses=2)
    ci_candidates = await field_library_migration_service.scan_ci_types(db, min_uses=2)
    
    plan = await field_library_migration_service.generate_migration_plan(
        db, forms_candidates, ci_candidates
    )
    return plan

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Optional, List

from app.core.database import get_db
from app.models.auth import User
from app.models.custom_fields import CustomFieldDefinition
from app.api.auth import get_current_developer
from app.services.data_query_service import ALLOWED_FIELD_TYPES, QUERYABLE_TABLES

router = APIRouter()


def _cf_to_dict(cf: CustomFieldDefinition) -> dict:
    return {
        "id": cf.id,
        "field_key": cf.field_key,
        "label": cf.label,
        "field_type": cf.field_type,
        "target_table": cf.target_table,
        "scope": cf.scope,
        "scope_id": cf.scope_id,
        "config": cf.config or {},
        "is_required": cf.is_required,
        "is_active": cf.is_active,
        "created_by": cf.created_by,
        "created_at": cf.created_at.isoformat() if cf.created_at else None,
        "updated_at": cf.updated_at.isoformat() if cf.updated_at else None,
    }


@router.get("/")
async def list_fields(
    target_table: Optional[str] = Query(None),
    scope: Optional[str] = Query(None),
    scope_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """List custom field definitions with optional filters."""
    conditions = []
    if target_table:
        if target_table not in QUERYABLE_TABLES:
            raise HTTPException(status_code=400, detail=f"Unknown table: {target_table}")
        conditions.append(CustomFieldDefinition.target_table == target_table)
    if scope:
        conditions.append(CustomFieldDefinition.scope == scope)
    if scope_id is not None:
        conditions.append(CustomFieldDefinition.scope_id == scope_id)
    if is_active is not None:
        conditions.append(CustomFieldDefinition.is_active == is_active)

    stmt = select(CustomFieldDefinition)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.order_by(CustomFieldDefinition.target_table, CustomFieldDefinition.label)

    result = await db.execute(stmt)
    fields = result.scalars().all()
    return [_cf_to_dict(f) for f in fields]


@router.post("/")
async def create_field(
    field_data: dict,
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """Create a new custom field definition."""
    target_table = field_data.get("target_table", "")
    if target_table not in QUERYABLE_TABLES:
        raise HTTPException(status_code=400, detail=f"Unknown or unsupported table: {target_table}")

    field_type = field_data.get("field_type", "string")
    if field_type not in ALLOWED_FIELD_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid field type: {field_type}. Allowed: {ALLOWED_FIELD_TYPES}")

    # Validate config for specific types
    config = field_data.get("config", {}) or {}
    if field_type == "select":
        options = config.get("options", [])
        if not options:
            raise HTTPException(status_code=400, detail="Select fields must have at least one option")
    elif field_type == "relationship":
        tgt_table = config.get("target_table", "")
        if tgt_table not in QUERYABLE_TABLES:
            raise HTTPException(status_code=400, detail=f"Invalid relationship target table: {tgt_table}")
        if not config.get("target_column"):
            raise HTTPException(status_code=400, detail="Relationship must specify target_column")
        if not config.get("display_column"):
            raise HTTPException(status_code=400, detail="Relationship must specify display_column")

    # Check uniqueness
    scope = field_data.get("scope", "global")
    scope_id = field_data.get("scope_id")
    field_key = field_data.get("field_key", "").strip().lower().replace(" ", "_")

    if not field_key:
        raise HTTPException(status_code=400, detail="field_key is required")

    check_stmt = select(CustomFieldDefinition).where(
        CustomFieldDefinition.field_key == field_key,
        CustomFieldDefinition.target_table == target_table,
        CustomFieldDefinition.scope == scope,
    )
    # Handle nullable scope_id comparison
    if scope_id is not None:
        check_stmt = check_stmt.where(CustomFieldDefinition.scope_id == scope_id)
    else:
        check_stmt = check_stmt.where(CustomFieldDefinition.scope_id.is_(None))

    check_result = await db.execute(check_stmt)
    if check_result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Field key already exists for this table/scope")

    cf = CustomFieldDefinition(
        field_key=field_key,
        label=field_data.get("label", field_key),
        field_type=field_type,
        target_table=target_table,
        scope=scope,
        scope_id=scope_id,
        config=config,
        is_required=field_data.get("is_required", False),
        is_active=True,
        created_by=current_user.id,
    )
    db.add(cf)
    await db.commit()
    await db.refresh(cf)

    # Audit log
    from app.services.data_query_service import log_custom_field_audit
    await log_custom_field_audit(
        db, current_user.id, "create_custom_field", "custom_field_definition", cf.id,
        f"Created field '{field_key}' on table '{target_table}'"
    )

    return _cf_to_dict(cf)


@router.get("/{field_id}")
async def get_field(
    field_id: int,
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """Get a single custom field definition."""
    stmt = select(CustomFieldDefinition).where(CustomFieldDefinition.id == field_id)
    result = await db.execute(stmt)
    cf = result.scalar_one_or_none()
    if not cf:
        raise HTTPException(status_code=404, detail="Custom field definition not found")
    return _cf_to_dict(cf)


@router.put("/{field_id}")
async def update_field(
    field_id: int,
    field_data: dict,
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """Update a custom field definition."""
    stmt = select(CustomFieldDefinition).where(CustomFieldDefinition.id == field_id)
    result = await db.execute(stmt)
    cf = result.scalar_one_or_none()
    if not cf:
        raise HTTPException(status_code=404, detail="Custom field definition not found")

    # Validate changes
    if "field_type" in field_data:
        ft = field_data["field_type"]
        if ft not in ALLOWED_FIELD_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid field type: {ft}")
        cf.field_type = ft

    if "config" in field_data:
        config = field_data["config"] or {}
        if cf.field_type == "select":
            if not config.get("options"):
                raise HTTPException(status_code=400, detail="Select fields must have at least one option")
        elif cf.field_type == "relationship":
            if config.get("target_table") and config["target_table"] not in QUERYABLE_TABLES:
                raise HTTPException(status_code=400, detail=f"Invalid relationship target table")
        cf.config = config

    for attr in ["label", "field_key", "target_table", "scope", "scope_id", "is_required", "is_active"]:
        if attr in field_data:
            setattr(cf, attr, field_data[attr])

    await db.commit()
    await db.refresh(cf)

    from app.services.data_query_service import log_custom_field_audit
    await log_custom_field_audit(
        db, current_user.id, "update_custom_field", "custom_field_definition", cf.id,
        f"Updated field '{cf.field_key}'"
    )

    return _cf_to_dict(cf)


@router.delete("/{field_id}")
async def delete_field(
    field_id: int,
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """Delete (deactivate) a custom field definition."""
    stmt = select(CustomFieldDefinition).where(CustomFieldDefinition.id == field_id)
    result = await db.execute(stmt)
    cf = result.scalar_one_or_none()
    if not cf:
        raise HTTPException(status_code=404, detail="Custom field definition not found")

    # Soft delete
    cf.is_active = False
    await db.commit()

    from app.services.data_query_service import log_custom_field_audit
    await log_custom_field_audit(
        db, current_user.id, "delete_custom_field", "custom_field_definition", cf.id,
        f"Deactivated field '{cf.field_key}' on table '{cf.target_table}'"
    )

    return {"message": f"Field '{cf.field_key}' deactivated"}

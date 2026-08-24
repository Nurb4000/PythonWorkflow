"""
CMDB API endpoints — CI Types, Configuration Items, Relationships.
"""
import json
import logging
import re
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, update
from sqlalchemy.orm import selectinload
from typing import Optional, List, Dict, Any

from app.core.database import get_db
from app.models.auth import User
from app.models.cmdb import CIType, ConfigurationItem, CIRelationship, CIHistory
from app.api.auth import get_current_developer, get_current_admin, get_current_cmdb_manager
from app.schemas.cmdb import (
    CITypeCreate, CITypeUpdate, CITypeResponse,
    CICreate, CIUpdate, CIResponse, CITypeDetailResponse,
    CIRelationshipCreate, CIRelationshipResponse,
    CIBulkImportRequest, CIBulkImportRecord,
    CIHistoryEntry, CMDBStatsResponse,
    ALLOWED_FIELD_TYPES,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    return re.sub(r'[^a-z0-9_]', '', name.lower().replace(' ', '_')) or "ci_type"


def _type_to_dict(ct: CIType, item_count: int = 0) -> Dict[str, Any]:
    return {
        "id": ct.id,
        "name": ct.name,
        "key": ct.key,
        "description": ct.description or "",
        "icon": ct.icon or "",
        "field_schema": ct.field_schema or [],
        "is_active": ct.is_active,
        "item_count": item_count,
        "created_at": ct.created_at.isoformat() if ct.created_at else None,
        "updated_at": ct.updated_at.isoformat() if ct.updated_at else None,
    }


def _ci_to_dict(ci: ConfigurationItem) -> Dict[str, Any]:
    return {
        "id": ci.id,
        "type_id": ci.type_id,
        "name": ci.name,
        "status": ci.status or "active",
        "ci_data": ci.ci_data or {},
        "custom_data": ci.custom_data or {},
        "created_by": ci.created_by,
        "updated_by": ci.updated_by,
        "created_at": ci.created_at.isoformat() if ci.created_at else None,
        "updated_at": ci.updated_at.isoformat() if ci.updated_at else None,
    }


def _ci_detail_to_dict(ci: ConfigurationItem) -> Dict[str, Any]:
    d = _ci_to_dict(ci)
    d["type_name"] = ci.ci_type.name if ci.ci_type else ""
    d["type_key"] = ci.ci_type.key if ci.ci_type else ""
    return d


def _rel_to_dict(rel: CIRelationship) -> Dict[str, Any]:
    return {
        "id": rel.id,
        "source_ci_id": rel.source_ci_id,
        "target_ci_id": rel.target_ci_id,
        "relationship_type": rel.relationship_type,
        "description": rel.description or "",
        "source_name": rel.source_ci.name if rel.source_ci else "",
        "target_name": rel.target_ci.name if rel.target_ci else "",
        "created_at": rel.created_at.isoformat() if rel.created_at else None,
    }


def _validate_field_schema(field_schema: list) -> List[str]:
    errors = []
    keys = set()
    for i, field in enumerate(field_schema):
        fd = field.model_dump() if hasattr(field, 'model_dump') else (field if isinstance(field, dict) else {})
        fk = str(fd.get("key", "")).strip()
        if not fk:
            errors.append(f"Field {i}: key is required")
        elif fk in keys:
            errors.append(f"Field {i}: duplicate key '{fk}'")
        else:
            keys.add(fk)

        ft = str(fd.get("type", ""))
        if ft not in ALLOWED_FIELD_TYPES:
            errors.append(f"Field {i}: invalid type '{ft}'. Allowed: {ALLOWED_FIELD_TYPES}")

        if ft == "select" and not fd.get("options"):
            errors.append(f"Field {i}: select fields must have at least one option")

    return errors


async def _record_history(db: AsyncSession, ci_id: int, changed_by: Optional[int], change_type: str, field_key: Optional[str], old_value: Any, new_value: Any):
    """Record a single history entry for a CI change."""
    entry = CIHistory(
        ci_id=ci_id,
        changed_by=changed_by,
        field_key=field_key,
        old_value=old_value if isinstance(old_value, dict) else (old_value if old_value is None else {"value": old_value}),
        new_value=new_value if isinstance(new_value, dict) else (new_value if new_value is None else {"value": new_value}),
        change_type=change_type,
    )
    db.add(entry)


async def _record_full_history(db: AsyncSession, ci_id: int, changed_by: Optional[int], change_type: str, old_ci_data: Dict[str, Any], new_ci_data: Dict[str, Any]):
    """Record field-level history for CI data changes."""
    all_keys = set(list(old_ci_data.keys()) + list(new_ci_data.keys()))
    for key in all_keys:
        old_val = old_ci_data.get(key)
        new_val = new_ci_data.get(key)
        if old_val != new_val:
            await _record_history(db, ci_id, changed_by, change_type, key, old_val, new_val)

    if not all_keys and change_type in ("create", "delete"):
        await _record_history(db, ci_id, changed_by, change_type, None, old_ci_data or None, new_ci_data or None)


# ---------------------------------------------------------------------------
# CI Type endpoints
# ---------------------------------------------------------------------------

@router.get("/types")
async def list_ci_types(
    include_inactive: bool = Query(False),
    search: Optional[str] = Query(None, description="Search by name or key"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """List all CI types with item counts. By default excludes deactivated types."""
    stmt = select(CIType)
    if not include_inactive:
        stmt = stmt.where(CIType.is_active == True)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(or_(CIType.name.ilike(pattern), CIType.key.ilike(pattern)))
    stmt = stmt.order_by(CIType.name)

    # A2: pagination
    offset = (page - 1) * page_size
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    stmt = stmt.offset(offset).limit(page_size)
    result = await db.execute(stmt)
    types = result.scalars().all()

    counts_stmt = select(
        ConfigurationItem.type_id,
        func.count(ConfigurationItem.id).label("cnt")
    ).group_by(ConfigurationItem.type_id)
    counts_result = await db.execute(counts_stmt)
    counts = dict(counts_result.all())

    return {
        "items": [_type_to_dict(t, counts.get(t.id, 0)) for t in types],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total else 0
    }


@router.post("/types", status_code=201)
async def create_ci_type(
    data: CITypeCreate,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new CI type (admin only)."""
    key = _slugify(data.name) if not data.key else data.key

    existing = await db.execute(select(CIType).where(
        or_(CIType.key == key, CIType.name == data.name)
    ))
    conflict = existing.scalar_one_or_none()
    if conflict:
        if conflict.key == key:
            raise HTTPException(status_code=409, detail=f"CI type key '{key}' already exists")
        raise HTTPException(status_code=409, detail=f"CI type name '{data.name}' already exists")

    schema_errors = _validate_field_schema(data.field_schema)
    if schema_errors:
        raise HTTPException(status_code=400, detail="Field schema errors: " + "; ".join(schema_errors))

    ct = CIType(
        name=data.name,
        key=key,
        description=data.description or "",
        icon=data.icon or "",
        field_schema=[f.model_dump() for f in data.field_schema],
    )
    db.add(ct)
    await db.commit()
    await db.refresh(ct)

    return _type_to_dict(ct)


@router.get("/types/{type_id}")
async def get_ci_type(
    type_id: int,
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """Get a single CI type."""
    stmt = select(CIType).where(CIType.id == type_id)
    result = await db.execute(stmt)
    ct = result.scalar_one_or_none()
    if not ct:
        raise HTTPException(status_code=404, detail="CI type not found")

    count_result = await db.execute(
        select(func.count(ConfigurationItem.id)).where(ConfigurationItem.type_id == type_id)
    )
    item_count = count_result.scalar() or 0

    return _type_to_dict(ct, item_count)


@router.put("/types/{type_id}")
async def update_ci_type(
    type_id: int,
    data: CITypeUpdate,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update a CI type (admin only)."""
    stmt = select(CIType).where(CIType.id == type_id)
    result = await db.execute(stmt)
    ct = result.scalar_one_or_none()
    if not ct:
        raise HTTPException(status_code=404, detail="CI type not found")

    if data.name is not None and data.name != ct.name:
        name_result = await db.execute(select(CIType).where(CIType.name == data.name, CIType.id != type_id))
        if name_result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail=f"CI type name '{data.name}' already exists")
        ct.name = data.name

    if data.key is not None and data.key != ct.key:
        key_result = await db.execute(select(CIType).where(CIType.key == data.key, CIType.id != type_id))
        if key_result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail=f"CI type key '{data.key}' already exists")
        ct.key = data.key

    if data.description is not None:
        ct.description = data.description
    if data.icon is not None:
        ct.icon = data.icon
    if data.is_active is not None:
        ct.is_active = data.is_active

    if data.field_schema is not None:
        schema_errors = _validate_field_schema(data.field_schema)
        if schema_errors:
            raise HTTPException(status_code=400, detail="Field schema errors: " + "; ".join(schema_errors))
        ct.field_schema = [f.model_dump() for f in data.field_schema]

    await db.commit()
    await db.refresh(ct)

    return _type_to_dict(ct)


@router.delete("/types/{type_id}")
async def delete_ci_type(
    type_id: int,
    cascade_deactivate_items: bool = Query(True, description="Also deactivate all items of this type"),
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a CI type. Optionally cascades deactivation to its items."""
    stmt = select(CIType).where(CIType.id == type_id)
    result = await db.execute(stmt)
    ct = result.scalar_one_or_none()
    if not ct:
        raise HTTPException(status_code=404, detail="CI type not found")

    count_result = await db.execute(
        select(func.count(ConfigurationItem.id)).where(ConfigurationItem.type_id == type_id)
    )
    item_count = count_result.scalar() or 0

    items_deactivated = 0
    if item_count > 0 and cascade_deactivate_items:
        update_stmt = (
            update(ConfigurationItem)
            .where(ConfigurationItem.type_id == type_id)
            .values(status="retired")
        )
        result = await db.execute(update_stmt)
        items_deactivated = result.rowcount or 0

    ct.is_active = False
    await db.commit()

    return {
        "message": f"CI type '{ct.name}' deactivated",
        "items_deactivated": items_deactivated,
    }


# ---------------------------------------------------------------------------
# Configuration Item endpoints
# ---------------------------------------------------------------------------

@router.get("/items")
async def list_cis(
    type_id: Optional[int] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    include_inactive: bool = Query(False),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    current_user: User = Depends(get_current_cmdb_manager),
    db: AsyncSession = Depends(get_db),
):
    """List configuration items with optional filters. By default excludes deactivated items."""
    stmt = select(ConfigurationItem).options(selectinload(ConfigurationItem.ci_type))

    conditions = []
    if not include_inactive:
        conditions.append(ConfigurationItem.is_active == True)
    if type_id is not None:
        conditions.append(ConfigurationItem.type_id == type_id)
    if status is not None:
        conditions.append(ConfigurationItem.status == status)
    if search:
        conditions.append(
            or_(
                ConfigurationItem.name.ilike(f"%{search}%"),
            )
        )

    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.order_by(ConfigurationItem.name)

    # A2: pagination
    offset = (page - 1) * page_size
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0
    
    stmt = stmt.offset(offset).limit(page_size)
    result = await db.execute(stmt)
    items = result.scalars().all()
    
    return {
        "items": [_ci_detail_to_dict(i) for i in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total else 0
    }


@router.post("/items", status_code=201)
async def create_ci(
    data: CICreate,
    current_user: User = Depends(get_current_cmdb_manager),
    db: AsyncSession = Depends(get_db),
):
    """Create a new configuration item."""
    type_stmt = select(CIType).where(CIType.id == data.type_id, CIType.is_active == True)
    type_result = await db.execute(type_stmt)
    ci_type = type_result.scalar_one_or_none()
    if not ci_type:
        raise HTTPException(status_code=404, detail="CI type not found or inactive")

    ci_data = data.ci_data or {}
    required_fields = [f["key"] for f in (ci_type.field_schema or []) if f.get("required")]
    missing = [k for k in required_fields if k not in ci_data]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required fields: {', '.join(missing)}"
        )

    ci = ConfigurationItem(
        type_id=data.type_id,
        name=data.name,
        status=data.status or "active",
        ci_data=ci_data,
        custom_data=data.custom_data or {},
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(ci)
    await db.flush()

    # Record creation history
    await _record_history(db, ci.id, current_user.id, "create", None, None, dict(ci.ci_data or {}))

    await db.commit()
    await db.refresh(ci)

    # Trigger webhook if configured
    await _trigger_cmdb_webhook(db, "ci_created", ci)

    return _ci_to_dict(ci)


# ---------------------------------------------------------------------------
# Export (must be before /items/{item_id} to avoid route conflict)
# ---------------------------------------------------------------------------

@router.get("/items/export")
async def export_cis(
    format: str = Query("json", regex="^(json|csv)$"),
    type_id: Optional[int] = None,
    current_user: User = Depends(get_current_cmdb_manager),
    db: AsyncSession = Depends(get_db),
):
    """Export CIs as JSON or CSV."""
    from fastapi.responses import Response

    stmt = select(ConfigurationItem).options(selectinload(ConfigurationItem.ci_type))
    if type_id is not None:
        stmt = stmt.where(ConfigurationItem.type_id == type_id)
    stmt = stmt.order_by(ConfigurationItem.name)
    result = await db.execute(stmt)
    items = result.scalars().all()

    if format == "csv":
        import io, csv
        if not items:
            return Response(content="", media_type="text/csv")

        # Collect all field keys across items
        all_keys = {"id", "type_id", "name", "status", "created_at", "updated_at"}
        for ci in items:
            all_keys.update((ci.ci_data or {}).keys())
        fieldnames = sorted(all_keys)

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for ci in items:
            row = {
                "id": ci.id,
                "type_id": ci.type_id,
                "name": ci.name,
                "status": ci.status or "",
                "created_at": ci.created_at.isoformat() if ci.created_at else "",
                "updated_at": ci.updated_at.isoformat() if ci.updated_at else "",
            }
            row.update(ci.ci_data or {})
            writer.writerow(row)

        return Response(content=output.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f"attachment; filename=cmdb_export_{type_id or 'all'}.csv"})
    else:
        data = [_ci_detail_to_dict(i) for i in items]
        return Response(content=json.dumps(data, indent=2, default=str), media_type="application/json",
                        headers={"Content-Disposition": f"attachment; filename=cmdb_export_{type_id or 'all'}.json"})


@router.get("/items/{item_id}")
async def get_ci(
    item_id: int,
    current_user: User = Depends(get_current_cmdb_manager),
    db: AsyncSession = Depends(get_db),
):
    """Get a single configuration item with type info."""
    stmt = select(ConfigurationItem).where(
        ConfigurationItem.id == item_id
    ).options(selectinload(ConfigurationItem.ci_type))
    result = await db.execute(stmt)
    ci = result.scalar_one_or_none()
    if not ci:
        raise HTTPException(status_code=404, detail="Configuration item not found")

    return _ci_detail_to_dict(ci)


@router.put("/items/{item_id}")
async def update_ci(
    item_id: int,
    data: CIUpdate,
    current_user: User = Depends(get_current_cmdb_manager),
    db: AsyncSession = Depends(get_db),
):
    """Update a configuration item."""
    stmt = select(ConfigurationItem).where(
        ConfigurationItem.id == item_id
    ).options(selectinload(ConfigurationItem.ci_type))
    result = await db.execute(stmt)
    ci = result.scalar_one_or_none()
    if not ci:
        raise HTTPException(status_code=404, detail="Configuration item not found")

    old_ci_data = dict(ci.ci_data or {})
    old_name = ci.name
    old_status = ci.status

    if data.name is not None:
        ci.name = data.name
    if data.status is not None:
        ci.status = data.status
    if data.ci_data is not None:
        required_fields = [f["key"] for f in (ci.ci_type.field_schema or []) if f.get("required")]
        missing = [k for k in required_fields if k not in data.ci_data]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required fields: {', '.join(missing)}"
            )
        ci.ci_data = data.ci_data
    if data.custom_data is not None:
        ci.custom_data = data.custom_data

    ci.updated_by = current_user.id

    # Record field-level history for name/status changes
    if data.name is not None and data.name != old_name:
        await _record_history(db, ci.id, current_user.id, "update", "name", old_name, data.name)
    if data.status is not None and data.status != old_status:
        await _record_history(db, ci.id, current_user.id, "update", "status", old_status, data.status)

    # Record field-level history for ci_data changes
    if data.ci_data is not None:
        await _record_full_history(db, ci.id, current_user.id, "update", old_ci_data, dict(data.ci_data))

    await db.commit()
    await db.refresh(ci)

    # Trigger webhook if configured
    if data.ci_data is not None:
        await _trigger_cmdb_webhook(db, "ci_updated", ci, old_data=old_ci_data)

    return _ci_to_dict(ci)


@router.delete("/items/{item_id}")
async def delete_ci(
    item_id: int,
    current_user: User = Depends(get_current_cmdb_manager),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a configuration item (soft-delete)."""
    stmt = select(ConfigurationItem).where(ConfigurationItem.id == item_id)
    result = await db.execute(stmt)
    ci = result.scalar_one_or_none()
    if not ci:
        raise HTTPException(status_code=404, detail="Configuration item not found")

    old_data = dict(ci.ci_data or {})

    # Record deactivation history
    await _record_history(db, ci.id, current_user.id, "delete", None, old_data, None)

    ci.is_active = False
    ci.status = "retired"
    await db.commit()

    # Trigger webhook if configured (pass ci data before deletion)
    await _trigger_cmdb_webhook(db, "ci_deleted", ci, old_data=old_data)

    return {"message": f"Configuration item '{ci.name}' deactivated"}


@router.get("/items/{item_id}/relationships")
async def get_ci_relationships(
    item_id: int,
    current_user: User = Depends(get_current_cmdb_manager),
    db: AsyncSession = Depends(get_db),
):
    """Get all relationships for a configuration item."""
    ci_stmt = select(ConfigurationItem).where(ConfigurationItem.id == item_id)
    ci_result = await db.execute(ci_stmt)
    if not ci_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Configuration item not found")

    stmt = select(CIRelationship).where(
        and_(
            or_(
                CIRelationship.source_ci_id == item_id,
                CIRelationship.target_ci_id == item_id,
            ),
            CIRelationship.is_active == True,
        )
    ).options(
        selectinload(CIRelationship.source_ci),
        selectinload(CIRelationship.target_ci),
    )
    result = await db.execute(stmt)
    rels = result.scalars().all()
    return [_rel_to_dict(r) for r in rels]


@router.get("/items/{item_id}/history")
async def get_ci_history(
    item_id: int,
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(get_current_cmdb_manager),
    db: AsyncSession = Depends(get_db),
):
    """Get audit history for a configuration item."""
    ci_stmt = select(ConfigurationItem).where(ConfigurationItem.id == item_id)
    ci_result = await db.execute(ci_stmt)
    if not ci_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Configuration item not found")

    stmt = select(CIHistory).where(CIHistory.ci_id == item_id)
    stmt = stmt.order_by(CIHistory.changed_at.desc()).limit(limit)
    result = await db.execute(stmt)
    entries = result.scalars().all()

    return [{
        "id": e.id,
        "ci_id": e.ci_id,
        "changed_by": e.changed_by,
        "changed_at": e.changed_at.isoformat() if e.changed_at else None,
        "field_key": e.field_key,
        "old_value": e.old_value,
        "new_value": e.new_value,
        "change_type": e.change_type,
    } for e in entries]


# ---------------------------------------------------------------------------
# Relationship endpoints
# ---------------------------------------------------------------------------

@router.post("/relationships", status_code=201)
async def create_relationship(
    data: CIRelationshipCreate,
    current_user: User = Depends(get_current_cmdb_manager),
    db: AsyncSession = Depends(get_db),
):
    """Create a relationship between two CIs."""
    if data.source_ci_id == data.target_ci_id:
        raise HTTPException(status_code=400, detail="Cannot create a self-referencing relationship")

    src_stmt = select(ConfigurationItem).where(ConfigurationItem.id == data.source_ci_id)
    src_result = await db.execute(src_stmt)
    if not src_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Source CI not found")

    tgt_stmt = select(ConfigurationItem).where(ConfigurationItem.id == data.target_ci_id)
    tgt_result = await db.execute(tgt_stmt)
    if not tgt_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Target CI not found")

    dup_stmt = select(CIRelationship).where(
        CIRelationship.source_ci_id == data.source_ci_id,
        CIRelationship.target_ci_id == data.target_ci_id,
        CIRelationship.relationship_type == data.relationship_type,
    )
    if (await db.execute(dup_stmt)).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="This relationship already exists")

    rel = CIRelationship(
        source_ci_id=data.source_ci_id,
        target_ci_id=data.target_ci_id,
        relationship_type=data.relationship_type,
        description=data.description or "",
    )
    db.add(rel)
    await db.commit()
    await db.refresh(rel)

    rel_stmt = select(rel.__class__).where(
        rel.__class__.id == rel.id
    ).options(
        selectinload(CIRelationship.source_ci),
        selectinload(CIRelationship.target_ci),
    )
    rel_result = await db.execute(rel_stmt)
    full_rel = rel_result.scalar_one()
    return _rel_to_dict(full_rel)


@router.delete("/relationships/{rel_id}")
async def delete_relationship(
    rel_id: int,
    current_user: User = Depends(get_current_cmdb_manager),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a relationship (soft-delete)."""
    stmt = select(CIRelationship).where(CIRelationship.id == rel_id)
    result = await db.execute(stmt)
    rel = result.scalar_one_or_none()
    if not rel:
        raise HTTPException(status_code=404, detail="Relationship not found")

    rel.is_active = False
    await db.commit()

    return {"message": "Relationship deactivated"}


# ---------------------------------------------------------------------------
# Bulk import
# ---------------------------------------------------------------------------

@router.post("/items/bulk-import")
async def bulk_import_cis(
    data: CIBulkImportRequest,
    current_user: User = Depends(get_current_cmdb_manager),
    db: AsyncSession = Depends(get_db),
):
    """Bulk import configuration items. Supports upsert by key field."""
    type_stmt = select(CIType).where(CIType.key == data.type_key, CIType.is_active == True)
    type_result = await db.execute(type_stmt)
    ci_type = type_result.scalar_one_or_none()
    if not ci_type:
        raise HTTPException(status_code=404, detail=f"Active CI type with key '{data.type_key}' not found")

    required_fields = [f["key"] for f in (ci_type.field_schema or []) if f.get("required")]
    created = 0
    updated = 0
    errors: List[Dict[str, Any]] = []

    for idx, record in enumerate(data.records):
        ci_data = record.ci_data or {}
        missing = [k for k in required_fields if k not in ci_data]
        if missing:
            errors.append({"index": idx, "name": record.name, "error": f"Missing required fields: {', '.join(missing)}"})
            continue

        existing_ci = None
        if data.upsert_key and data.upsert_key in ci_data:
            upsert_val = ci_data[data.upsert_key]
            type_cis_stmt = select(ConfigurationItem).where(
                ConfigurationItem.type_id == ci_type.id,
            )
            type_cis_result = await db.execute(type_cis_stmt)
            type_cis = type_cis_result.scalars().all()
            for tc in type_cis:
                tc_data = tc.ci_data or {}
                if tc_data.get(data.upsert_key) == upsert_val:
                    existing_ci = tc
                    break

        if existing_ci:
            existing_ci.name = record.name
            existing_ci.status = record.status or "active"
            existing_ci.ci_data = ci_data
            existing_ci.updated_by = current_user.id
            updated += 1
        else:
            new_ci = ConfigurationItem(
                type_id=ci_type.id,
                name=record.name,
                status=record.status or "active",
                ci_data=ci_data,
                created_by=current_user.id,
                updated_by=current_user.id,
            )
            db.add(new_ci)
            created += 1

    if not data.dry_run:
        await db.commit()
    else:
        await db.rollback()

    return {
        "dry_run": data.dry_run,
        "created": created,
        "updated": updated,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@router.get("/search")
async def search_cis(
    q: str = Query(..., min_length=1, description="Search query"),
    type_id: Optional[int] = None,
    current_user: User = Depends(get_current_cmdb_manager),
    db: AsyncSession = Depends(get_db),
):
    """Full-text search across CI names and ci_data values."""
    stmt = select(ConfigurationItem).options(selectinload(ConfigurationItem.ci_type))
    conditions = [ConfigurationItem.name.ilike(f"%{q}%")]

    if type_id is not None:
        conditions.append(ConfigurationItem.type_id == type_id)

    stmt = stmt.where(or_(*conditions))
    stmt = stmt.order_by(ConfigurationItem.name)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return [_ci_detail_to_dict(i) for i in items]


# ---------------------------------------------------------------------------
# Relationship graph (simple adjacency, depth-limited)
# ---------------------------------------------------------------------------

@router.get("/items/{item_id}/graph")
async def get_ci_graph(
    item_id: int,
    depth: int = Query(1, ge=1, le=5),
    current_user: User = Depends(get_current_cmdb_manager),
    db: AsyncSession = Depends(get_db),
):
    """Return adjacency graph for impact analysis."""
    ci_stmt = select(ConfigurationItem).where(ConfigurationItem.id == item_id)
    ci_result = await db.execute(ci_stmt)
    root_ci = ci_result.scalar_one_or_none()
    if not root_ci:
        raise HTTPException(status_code=404, detail="Configuration item not found")

    visited = {item_id}
    nodes = [{"id": root_ci.id, "name": root_ci.name, "type_id": root_ci.type_id}]
    edges = []

    frontier = [item_id]
    for _ in range(depth):
        next_frontier = []
        rel_stmt = select(CIRelationship).where(
            CIRelationship.source_ci_id.in_(frontier) if frontier else False
        ).options(
            selectinload(CIRelationship.source_ci),
            selectinload(CIRelationship.target_ci),
        )
        rel_result = await db.execute(rel_stmt)
        for rel in rel_result.scalars().all():
            edges.append({
                "source": rel.source_ci_id,
                "target": rel.target_ci_id,
                "type": rel.relationship_type,
            })
            if rel.target_ci_id not in visited:
                visited.add(rel.target_ci_id)
                next_frontier.append(rel.target_ci_id)
                if rel.target_ci:
                    nodes.append({
                        "id": rel.target_ci.id,
                        "name": rel.target_ci.name,
                        "type_id": rel.target_ci.type_id,
                    })
        frontier = next_frontier
        if not frontier:
            break

    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Webhook trigger on CI events
# ---------------------------------------------------------------------------

async def _trigger_cmdb_webhook(db: AsyncSession, event_type: str, ci: ConfigurationItem, old_data: Optional[Dict[str, Any]] = None):
    """If the CI type has a webhook workflow configured, trigger it."""
    try:
        from app.models.schemas import Workflow
        from app.models.system_settings import SystemSetting
        from app.services.scheduler import scheduler_service

        ci_type_id = ci.type_id
        if not ci_type_id:
            return

        # Look up webhook workflow ID from system settings
        setting_key = f"cmdb_webhook_workflow_{ci_type_id}"
        stmt = select(SystemSetting).where(SystemSetting.key == setting_key)
        result = await db.execute(stmt)
        setting = result.scalar_one_or_none()
        if not setting:
            return

        webhook_workflow_id = int(setting.value)

        # Verify workflow exists
        wf_stmt = select(Workflow).where(Workflow.id == webhook_workflow_id, Workflow.is_active == True)
        wf_result = await db.execute(wf_stmt)
        if not wf_result.scalar_one_or_none():
            return

        # Fetch CI type info
        type_stmt = select(CIType).where(CIType.id == ci_type_id)
        type_result = await db.execute(type_stmt)
        ci_type = type_result.scalar_one_or_none()

        payload = {
            "event": event_type,
            "ci_id": ci.id,
            "ci_name": ci.name,
            "ci_status": ci.status,
            "ci_data": ci.ci_data or {},
            "ci_type_name": ci_type.name if ci_type else "",
            "ci_type_key": ci_type.key if ci_type else "",
        }
        if old_data:
            payload["old_data"] = old_data

        await scheduler_service.trigger_webhook(webhook_workflow_id, payload)
    except Exception as e:
        logger.warning(f"CMDB webhook trigger failed: {e}")


@router.post("/types/{type_id}/webhook")
async def configure_type_webhook(
    type_id: int,
    data: dict,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Configure a webhook workflow for CI events on this type.

    Body: {"workflow_id": 123} or {"workflow_id": null} to disable
    """
    stmt = select(CIType).where(CIType.id == type_id)
    result = await db.execute(stmt)
    ct = result.scalar_one_or_none()
    if not ct:
        raise HTTPException(status_code=404, detail="CI type not found")

    workflow_id = data.get("workflow_id")
    # Store in ci_type config (we need to add a config column to CIType)
    # For now, use a system_settings key per type
    from app.models.system_settings import SystemSetting
    setting_key = f"cmdb_webhook_workflow_{type_id}"

    existing_stmt = select(SystemSetting).where(SystemSetting.key == setting_key)
    existing_result = await db.execute(existing_stmt)
    existing = existing_result.scalar_one_or_none()

    if workflow_id is None:
        # Disable webhook
        if existing:
            await db.delete(existing)
    else:
        if existing:
            existing.value = str(workflow_id)
        else:
            new_setting = SystemSetting(key=setting_key, value=str(workflow_id))
            db.add(new_setting)

    await db.commit()

    return {"message": "Webhook configured", "type_id": type_id, "workflow_id": workflow_id}


@router.get("/types/{type_id}/webhook")
async def get_type_webhook(
    type_id: int,
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """Get the webhook workflow configured for this CI type."""
    stmt = select(CIType).where(CIType.id == type_id)
    result = await db.execute(stmt)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="CI type not found")

    from app.models.system_settings import SystemSetting
    setting_key = f"cmdb_webhook_workflow_{type_id}"
    existing_stmt = select(SystemSetting).where(SystemSetting.key == setting_key)
    existing_result = await db.execute(existing_stmt)
    existing = existing_result.scalar_one_or_none()

    workflow_id = int(existing.value) if existing else None

    return {"type_id": type_id, "workflow_id": workflow_id}


# ---------------------------------------------------------------------------
# Stats endpoint
# ---------------------------------------------------------------------------

@router.get("/stats")
async def get_cmdb_stats(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """Get CMDB statistics for dashboard widgets."""
    from datetime import timedelta

    total_types = (await db.execute(select(func.count(CIType.id)).where(CIType.is_active == True))).scalar() or 0
    total_items = (await db.execute(select(func.count(ConfigurationItem.id)))).scalar() or 0

    # Items by status
    status_result = await db.execute(
        select(ConfigurationItem.status, func.count(ConfigurationItem.id).label("cnt"))
        .group_by(ConfigurationItem.status)
    )
    items_by_status = {row[0]: row[1] for row in status_result.all()}

    # Items by type
    type_result = await db.execute(
        select(
            CIType.id, CIType.name, CIType.icon,
            func.count(ConfigurationItem.id).label("cnt")
        )
        .outerjoin(ConfigurationItem, ConfigurationItem.type_id == CIType.id)
        .where(CIType.is_active == True)
        .group_by(CIType.id, CIType.name, CIType.icon)
        .order_by(func.count(ConfigurationItem.id).desc())
    )
    items_by_type = [{"type_id": r[0], "type_name": r[1], "icon": r[2] or "", "count": r[3]} for r in type_result.all()]

    # Recent changes count
    cutoff = func.now() - timedelta(days=days)
    recent_changes = (await db.execute(
        select(func.count(CIHistory.id)).where(CIHistory.changed_at >= cutoff)
    )).scalar() or 0

    return {
        "total_types": total_types,
        "total_items": total_items,
        "items_by_status": items_by_status,
        "items_by_type": items_by_type,
        "recent_changes": recent_changes,
    }


# ---------------------------------------------------------------------------
# Templates endpoint
# ---------------------------------------------------------------------------

CI_TYPE_TEMPLATES = [
    {
        "name": "Server",
        "key": "server",
        "icon": "",
        "description": "Physical or virtual server",
        "field_schema": [
            {"key": "hostname", "label": "Hostname", "type": "string", "required": True},
            {"key": "ip_address", "label": "IP Address", "type": "string", "required": False, "validation": "ipv4"},
            {"key": "cpu_cores", "label": "CPU Cores", "type": "number", "required": False},
            {"key": "ram_gb", "label": "RAM (GB)", "type": "number", "required": False},
            {"key": "os", "label": "Operating System", "type": "select", "options": ["Ubuntu 20.04", "Ubuntu 22.04", "RHEL 8", "RHEL 9", "Windows Server 2019", "Windows Server 2022"]},
            {"key": "environment", "label": "Environment", "type": "select", "options": ["dev", "staging", "prod"]},
            {"key": "datacenter", "label": "Data Center", "type": "string", "required": False},
            {"key": "install_date", "label": "Install Date", "type": "date"},
            {"key": "notes", "label": "Notes", "type": "text"},
        ],
    },
    {
        "name": "Network Device",
        "key": "network_device",
        "icon": "",
        "description": "Switch, router, firewall, or load balancer",
        "field_schema": [
            {"key": "hostname", "label": "Hostname", "type": "string", "required": True},
            {"key": "management_ip", "label": "Management IP", "type": "string", "required": True, "validation": "ipv4"},
            {"key": "device_type", "label": "Device Type", "type": "select", "options": ["switch", "router", "firewall", "load_balancer", "access_point"]},
            {"key": "vendor", "label": "Vendor", "type": "string", "required": False},
            {"key": "model", "label": "Model", "type": "string", "required": False},
            {"key": "firmware_version", "label": "Firmware Version", "type": "string", "required": False},
            {"key": "location", "label": "Location", "type": "string", "required": False},
            {"key": "serial_number", "label": "Serial Number", "type": "string", "required": False},
            {"key": "notes", "label": "Notes", "type": "text"},
        ],
    },
    {
        "name": "Application",
        "key": "application",
        "icon": "",
        "description": "Software application or service",
        "field_schema": [
            {"key": "app_name", "label": "Application Name", "type": "string", "required": True},
            {"key": "version", "label": "Version", "type": "string", "required": False},
            {"key": "owner", "label": "Owner / Team", "type": "string", "required": False},
            {"key": "url", "label": "URL", "type": "url", "required": False},
            {"key": "environment", "label": "Environment", "type": "select", "options": ["dev", "staging", "prod"]},
            {"key": "tech_stack", "label": "Technology Stack", "type": "text", "required": False},
            {"key": "license_type", "label": "License Type", "type": "select", "options": ["open_source", "commercial", "internal"]},
            {"key": "deploy_date", "label": "Deploy Date", "type": "date"},
            {"key": "notes", "label": "Notes", "type": "text"},
        ],
    },
    {
        "name": "Database",
        "key": "database",
        "icon": "",
        "description": "Database instance or cluster",
        "field_schema": [
            {"key": "db_name", "label": "Database Name", "type": "string", "required": True},
            {"key": "engine", "label": "Engine", "type": "select", "options": ["PostgreSQL", "MySQL", "MongoDB", "Redis", "Oracle", "SQL Server"]},
            {"key": "version", "label": "Version", "type": "string", "required": False},
            {"key": "host", "label": "Host", "type": "string", "required": False},
            {"key": "port", "label": "Port", "type": "number", "required": False},
            {"key": "environment", "label": "Environment", "type": "select", "options": ["dev", "staging", "prod"]},
            {"key": "storage_gb", "label": "Storage (GB)", "type": "number", "required": False},
            {"key": "backup_enabled", "label": "Backup Enabled", "type": "boolean"},
            {"key": "owner", "label": "Owner / Team", "type": "string", "required": False},
            {"key": "notes", "label": "Notes", "type": "text"},
        ],
    },
    {
        "name": "Cloud Instance",
        "key": "cloud_instance",
        "icon": "",
        "description": "Cloud VM or container instance",
        "field_schema": [
            {"key": "instance_id", "label": "Instance ID", "type": "string", "required": True},
            {"key": "provider", "label": "Cloud Provider", "type": "select", "options": ["AWS", "Azure", "GCP", "DigitalOcean"]},
            {"key": "region", "label": "Region", "type": "string", "required": False},
            {"key": "instance_type", "label": "Instance Type", "type": "string", "required": False},
            {"key": "public_ip", "label": "Public IP", "type": "string", "required": False, "validation": "ipv4"},
            {"key": "private_ip", "label": "Private IP", "type": "string", "required": False, "validation": "ipv4"},
            {"key": "environment", "label": "Environment", "type": "select", "options": ["dev", "staging", "prod"]},
            {"key": "launch_date", "label": "Launch Date", "type": "date"},
            {"key": "monthly_cost", "label": "Estimated Monthly Cost ($)", "type": "number", "required": False},
            {"key": "tags", "label": "Tags", "type": "text", "required": False},
            {"key": "notes", "label": "Notes", "type": "text"},
        ],
    },
]


@router.get("/templates")
async def list_templates(
    current_user: User = Depends(get_current_developer),
):
    """List pre-built CI type templates."""
    return CI_TYPE_TEMPLATES


@router.post("/templates/{template_key}/apply", status_code=201)
async def apply_template(
    template_key: str,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Apply a pre-built CI type template (admin only)."""
    template = next((t for t in CI_TYPE_TEMPLATES if t["key"] == template_key), None)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template '{template_key}' not found")

    existing = await db.execute(select(CIType).where(CIType.key == template["key"]))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"CI type '{template['name']}' already exists")

    schema_errors = _validate_field_schema(template["field_schema"])
    if schema_errors:
        raise HTTPException(status_code=500, detail=f"Template validation error: {'; '.join(schema_errors)}")

    ct = CIType(
        name=template["name"],
        key=template["key"],
        description=template["description"] or "",
        icon=template.get("icon", "") or "",
        field_schema=template["field_schema"],
    )
    db.add(ct)
    await db.commit()
    await db.refresh(ct)

    return _type_to_dict(ct)

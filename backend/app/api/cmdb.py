"""
CMDB API endpoints — CI Types, Configuration Items, Relationships.
"""
import re
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload
from typing import Optional, List, Dict, Any

from app.core.database import get_db
from app.models.auth import User
from app.models.cmdb import CIType, ConfigurationItem, CIRelationship
from app.api.auth import get_current_developer, get_current_admin
from app.schemas.cmdb import (
    CITypeCreate, CITypeUpdate, CITypeResponse,
    CICreate, CIUpdate, CIResponse, CITypeDetailResponse,
    CIRelationshipCreate, CIRelationshipResponse,
    CIBulkImportRequest, CIBulkImportRecord,
    ALLOWED_FIELD_TYPES,
)

router = APIRouter()


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


# ---------------------------------------------------------------------------
# CI Type endpoints
# ---------------------------------------------------------------------------

@router.get("/types")
async def list_ci_types(
    is_active: Optional[bool] = None,
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """List all CI types with item counts."""
    stmt = select(CIType)
    if is_active is not None:
        stmt = stmt.where(CIType.is_active == is_active)
    stmt = stmt.order_by(CIType.name)

    result = await db.execute(stmt)
    types = result.scalars().all()

    counts_stmt = select(
        ConfigurationItem.type_id,
        func.count(ConfigurationItem.id).label("cnt")
    ).group_by(ConfigurationItem.type_id)
    counts_result = await db.execute(counts_stmt)
    counts = dict(counts_result.all())

    return [_type_to_dict(t, counts.get(t.id, 0)) for t in types]


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
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a CI type (admin only). Fails if items exist."""
    stmt = select(CIType).where(CIType.id == type_id)
    result = await db.execute(stmt)
    ct = result.scalar_one_or_none()
    if not ct:
        raise HTTPException(status_code=404, detail="CI type not found")

    count_result = await db.execute(
        select(func.count(ConfigurationItem.id)).where(ConfigurationItem.type_id == type_id)
    )
    if (count_result.scalar() or 0) > 0:
        raise HTTPException(status_code=409, detail="Cannot delete CI type that has items. Delete or reassign items first.")

    ct.is_active = False
    await db.commit()

    return {"message": f"CI type '{ct.name}' deactivated"}


# ---------------------------------------------------------------------------
# Configuration Item endpoints
# ---------------------------------------------------------------------------

@router.get("/items")
async def list_cis(
    type_id: Optional[int] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """List configuration items with optional filters."""
    stmt = select(ConfigurationItem).options(selectinload(ConfigurationItem.ci_type))

    conditions = []
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

    result = await db.execute(stmt)
    items = result.scalars().all()
    return [_ci_detail_to_dict(i) for i in items]


@router.post("/items", status_code=201)
async def create_ci(
    data: CICreate,
    current_user: User = Depends(get_current_developer),
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
    await db.commit()
    await db.refresh(ci)

    return _ci_to_dict(ci)


@router.get("/items/{item_id}")
async def get_ci(
    item_id: int,
    current_user: User = Depends(get_current_developer),
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
    current_user: User = Depends(get_current_developer),
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
    await db.commit()
    await db.refresh(ci)

    return _ci_to_dict(ci)


@router.delete("/items/{item_id}")
async def delete_ci(
    item_id: int,
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """Delete a configuration item."""
    stmt = select(ConfigurationItem).where(ConfigurationItem.id == item_id)
    result = await db.execute(stmt)
    ci = result.scalar_one_or_none()
    if not ci:
        raise HTTPException(status_code=404, detail="Configuration item not found")

    await db.delete(ci)
    await db.commit()

    return {"message": f"Configuration item '{ci.name}' deleted"}


@router.get("/items/{item_id}/relationships")
async def get_ci_relationships(
    item_id: int,
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """Get all relationships for a configuration item."""
    ci_stmt = select(ConfigurationItem).where(ConfigurationItem.id == item_id)
    ci_result = await db.execute(ci_stmt)
    if not ci_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Configuration item not found")

    stmt = select(CIRelationship).where(
        or_(
            CIRelationship.source_ci_id == item_id,
            CIRelationship.target_ci_id == item_id,
        )
    ).options(
        selectinload(CIRelationship.source_ci),
        selectinload(CIRelationship.target_ci),
    )
    result = await db.execute(stmt)
    rels = result.scalars().all()
    return [_rel_to_dict(r) for r in rels]


# ---------------------------------------------------------------------------
# Relationship endpoints
# ---------------------------------------------------------------------------

@router.post("/relationships", status_code=201)
async def create_relationship(
    data: CIRelationshipCreate,
    current_user: User = Depends(get_current_developer),
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
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """Delete a relationship."""
    stmt = select(CIRelationship).where(CIRelationship.id == rel_id)
    result = await db.execute(stmt)
    rel = result.scalar_one_or_none()
    if not rel:
        raise HTTPException(status_code=404, detail="Relationship not found")

    await db.delete(rel)
    await db.commit()

    return {"message": "Relationship deleted"}


# ---------------------------------------------------------------------------
# Bulk import
# ---------------------------------------------------------------------------

@router.post("/items/bulk-import")
async def bulk_import_cis(
    data: CIBulkImportRequest,
    current_user: User = Depends(get_current_developer),
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
    current_user: User = Depends(get_current_developer),
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
    current_user: User = Depends(get_current_developer),
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

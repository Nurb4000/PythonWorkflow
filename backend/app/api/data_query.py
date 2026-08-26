import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List, Dict, Any

from app.core.database import get_db
from app.models.auth import User
from app.api.auth import get_current_developer, get_current_user
from app.services.data_query_service import (
    list_tables_with_fields,
    execute_visual_query,
    execute_sql_query,
    update_custom_data,
    bulk_update_custom_data,
    QUERYABLE_TABLES,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/tables")
async def list_tables(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all queryable tables with security filtering."""
    try:
        from app.services.query_security_service import query_security_service
        
        # Get allowed tables for this user
        allowed_tables = await query_security_service.get_allowed_tables(db, current_user)
        
        # Get full table list
        result = await list_tables_with_fields(db)
        
        # Filter by allowed tables
        if allowed_tables:
            filtered = [t for t in result if t["table"] in allowed_tables]
            return {"tables": filtered, "total": len(filtered), "allowed_count": len(allowed_tables)}
        
        return {"tables": result, "total": len(result), "allowed_count": len(result)}
    except Exception as e:
        logger.error(f"Failed to list tables: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load tables: {str(e)}")


@router.post("/build")
async def run_visual_query(
    query_body: Dict[str, Any],
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """Execute a visual filter builder query with security filtering."""
    table_name = query_body.get("table", "")
    if table_name not in QUERYABLE_TABLES:
        raise HTTPException(status_code=400, detail=f"Unknown table: {table_name}")

    # Check access permission
    from app.services.query_security_service import query_security_service
    has_access = await query_security_service.validate_query_access(
        db, current_user, table_name, "view"
    )
    if not has_access:
        raise HTTPException(status_code=403, detail=f"Access denied to table: {table_name}")

    try:
        result = await execute_visual_query(
            db,
            table_name=table_name,
            filters=query_body.get("filters"),
            logic=query_body.get("logic", "AND"),
            sort_by=query_body.get("sort_by"),
            sort_order=query_body.get("sort_order", "asc"),
            limit=min(query_body.get("limit", 100), 10000),
            offset=query_body.get("offset", 0),
            custom_field_scope_id=query_body.get("custom_field_scope_id"),
        )
        
        # Filter results based on visible fields
        if "results" in result:
            result["results"] = await query_security_service.filter_query_results(
                db, current_user, table_name, result["results"], "view"
            )
        
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sql")
async def run_sql_query(
    query_body: Dict[str, str],
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """Execute a raw SQL query (read-only, admin/developer only)."""
    sql = query_body.get("sql", "").strip()
    if not sql:
        raise HTTPException(status_code=400, detail="SQL query is required")

    try:
        async def _run():
            return await execute_sql_query(db, sql, max_rows=10000)

        result = await asyncio.wait_for(_run(), timeout=30.0)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except asyncio.TimeoutError:
        raise HTTPException(status_code=408, detail="Query timed out after 30 seconds")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query execution failed: {str(e)}")


@router.put("/records/{table_name}/{record_id}/custom-data")
async def update_record_custom_data(
    table_name: str,
    record_id: int,
    data: Dict[str, Any],
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """Update a custom_data field on a specific record.

    Body: { "field_key": "cost_center", "value": "CC-101" }
    """
    if table_name not in QUERYABLE_TABLES:
        raise HTTPException(status_code=400, detail=f"Unknown table: {table_name}")

    field_key = data.get("field_key")
    value = data.get("value")
    if not field_key:
        raise HTTPException(status_code=400, detail="field_key is required")

    success = await update_custom_data(db, table_name, record_id, field_key, value)
    if not success:
        raise HTTPException(status_code=404, detail=f"Record {record_id} not found in {table_name}")

    # Audit log
    from app.services.data_query_service import log_custom_field_audit
    await log_custom_field_audit(
        db, current_user.id, "update_custom_data", table_name, record_id,
        f"Set '{field_key}' = {value!r}"
    )

    return {"message": f"Updated {field_key} on {table_name}.{record_id}", "success": True}


@router.post("/bulk-update/custom-data")
async def bulk_update_custom_data_endpoint(
    data: Dict[str, Any],
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """Bulk update a custom_data field on multiple records.

    Body: {
      "table": "tasks",
      "record_ids": [1, 2, 3],
      "field_key": "cost_center",
      "value": "CC-101"
    }
    """
    table_name = data.get("table", "")
    if table_name not in QUERYABLE_TABLES:
        raise HTTPException(status_code=400, detail=f"Unknown table: {table_name}")

    record_ids = data.get("record_ids", [])
    field_key = data.get("field_key", "")
    value = data.get("value")

    if not record_ids:
        raise HTTPException(status_code=400, detail="record_ids is required and must not be empty")
    if not field_key:
        raise HTTPException(status_code=400, detail="field_key is required")

    count = await bulk_update_custom_data(db, table_name, record_ids, field_key, value)

    from app.services.data_query_service import log_custom_field_audit
    await log_custom_field_audit(
        db, current_user.id, "bulk_update_custom_data", table_name, None,
        f"Set '{field_key}' = {value!r} on {count} records (ids: {record_ids[:10]}...)"
    )

    return {"message": f"Updated {count} records", "count": count}

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List

from app.core.database import get_db
from app.models.auth import User
from app.api.auth import get_current_developer
from app.services.data_query_service import (
    export_table_to_csv,
    export_query_to_csv,
    execute_visual_query,
    QUERYABLE_TABLES,
)

router = APIRouter()


@router.get("/table/{table_name}")
async def export_table(
    table_name: str,
    columns: Optional[str] = Query(None, description="Comma-separated column names"),
    limit: int = Query(10000, ge=1, le=100000),
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """Export an entire table to CSV."""
    if table_name not in QUERYABLE_TABLES:
        raise HTTPException(status_code=400, detail=f"Unknown table: {table_name}")

    # Enforce table-level view access (same guard as /data-query/build). Without
    # this any developer could dump any queryable table; combined with the
    # secret-column denylist in the service this closes findings #26.
    from app.services.query_security_service import query_security_service
    has_access = await query_security_service.validate_query_access(
        db, current_user, table_name, "view"
    )
    if not has_access:
        raise HTTPException(status_code=403, detail=f"Access denied to table: {table_name}")

    col_list = [c.strip() for c in columns.split(",")] if columns else None

    try:
        csv_content = await export_table_to_csv(
            db, table_name, col_list, limit, current_user=current_user
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={table_name}_export.csv"
        },
    )


@router.post("/query")
async def export_query(
    query_body: dict,
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """Export visual query results to CSV.

    Body same as /data-query/build endpoint.
    """
    table_name = query_body.get("table", "")
    if table_name not in QUERYABLE_TABLES:
        raise HTTPException(status_code=400, detail=f"Unknown table: {table_name}")

    # Enforce table-level view access before running the query/export.
    from app.services.query_security_service import query_security_service
    has_access = await query_security_service.validate_query_access(
        db, current_user, table_name, "view"
    )
    if not has_access:
        raise HTTPException(status_code=403, detail=f"Access denied to table: {table_name}")

    try:
        csv_content = await export_query_to_csv(
            db,
            table_name=table_name,
            filters=query_body.get("filters"),
            logic=query_body.get("logic", "AND"),
            sort_by=query_body.get("sort_by"),
            sort_order=query_body.get("sort_order", "asc"),
            limit=min(query_body.get("limit", 10000), 100000),
            current_user=current_user,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=query_{table_name}_export.csv"
        },
    )

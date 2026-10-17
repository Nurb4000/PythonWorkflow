"""
F2: Report definitions API — CRUD for report definitions, execute reports.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from typing import List, Optional

from app.core.database import get_db
from app.models.auth import User
from app.api.auth import get_current_admin, get_current_user
from app.models.reports import ReportDefinition

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/")
async def list_report_definitions(
    is_active: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List report definitions."""
    stmt = select(ReportDefinition)
    if is_active is not None:
        stmt = stmt.where(ReportDefinition.is_active == is_active)
    
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0
    
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size).order_by(ReportDefinition.name)
    
    result = await db.execute(stmt)
    reports = result.scalars().all()
    
    return {
        "items": [
            {
                "id": r.id,
                "name": r.name,
                "description": r.description,
                "view_name": r.view_name,
                "columns": r.columns or [],
                "filters": r.filters or [],
                "sort_by": r.sort_by,
                "sort_order": r.sort_order,
                "limit": r.limit,
                "schedule_cron": r.schedule_cron,
                "export_format": r.export_format,
                "owner_user_id": r.owner_user_id,
                "tags": r.tags or [],
                "is_active": r.is_active,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reports
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total else 0
    }


@router.get("/{report_id}")
async def get_report_definition(
    report_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a single report definition."""
    stmt = select(ReportDefinition).where(ReportDefinition.id == report_id)
    result = await db.execute(stmt)
    report = result.scalar_one_or_none()
    
    if not report:
        raise HTTPException(status_code=404, detail="Report definition not found")
    
    return {
        "id": report.id,
        "name": report.name,
        "description": report.description,
        "view_name": report.view_name,
        "columns": report.columns or [],
        "filters": report.filters or [],
        "sort_by": report.sort_by,
        "sort_order": report.sort_order,
        "limit": report.limit,
        "schedule_cron": report.schedule_cron,
        "export_format": report.export_format,
        "owner_user_id": report.owner_user_id,
        "tags": report.tags or [],
        "is_active": report.is_active,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "updated_at": report.updated_at.isoformat() if report.updated_at else None,
    }


@router.post("/", status_code=201)
async def create_report_definition(
    data: dict,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a new report definition (admin only)."""
    name = data.get("name")
    view_name = data.get("view_name")
    
    if not name or not view_name:
        raise HTTPException(status_code=400, detail="name and view_name are required")
    
    report = ReportDefinition(
        name=name,
        description=data.get("description", ""),
        view_name=view_name,
        columns=data.get("columns", []),
        filters=data.get("filters", []),
        sort_by=data.get("sort_by", ""),
        sort_order=data.get("sort_order", "asc"),
        limit=data.get("limit", 100),
        schedule_cron=data.get("schedule_cron"),
        export_format=data.get("export_format", "csv"),
        owner_user_id=current_user.id,
        tags=data.get("tags", []),
        is_active=data.get("is_active", True)
    )
    
    db.add(report)
    await db.commit()
    await db.refresh(report)
    
    return {"id": report.id, "name": report.name, "message": "Report definition created"}


@router.put("/{report_id}")
async def update_report_definition(
    report_id: int,
    data: dict,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update a report definition (admin only)."""
    stmt = select(ReportDefinition).where(ReportDefinition.id == report_id)
    result = await db.execute(stmt)
    report = result.scalar_one_or_none()
    
    if not report:
        raise HTTPException(status_code=404, detail="Report definition not found")
    
    for field in ["name", "description", "view_name", "columns", "filters", 
                  "sort_by", "sort_order", "limit", "schedule_cron", 
                  "export_format", "tags", "is_active"]:
        if field in data:
            setattr(report, field, data[field])
    
    await db.commit()
    await db.refresh(report)
    
    return {"message": "Report definition updated", "id": report.id}


@router.post("/{report_id}/execute")
async def execute_report(
    report_id: int,
    params: dict = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Execute a report definition and return results."""
    stmt = select(ReportDefinition).where(ReportDefinition.id == report_id)
    result = await db.execute(stmt)
    report = result.scalar_one_or_none()
    
    if not report:
        raise HTTPException(status_code=404, detail="Report definition not found")
    
    # Build dynamic SQL based on report config
    view_name = report.view_name
    columns = report.columns or []
    filters = report.filters or []
    sort_by = report.sort_by or "id"
    sort_order = report.sort_order or "asc"
    limit = report.limit or 100
    
    # Select columns
    if columns:
        select_cols = []
        for col in columns:
            if isinstance(col, dict):
                field = col.get("field", "")
                alias = col.get("label", field)
                if field:
                    select_cols.append(f'"{field}" as "{alias}"')
        if not select_cols:
            select_cols = ["*"]
    else:
        select_cols = ["*"]
    
    select_sql = ", ".join(select_cols)
    
    # WHERE filters
    where_clauses = []
    if filters:
        for f in filters:
            if isinstance(f, dict):
                field = f.get("field", "")
                operator = f.get("operator", "=")
                value = f.get("value")
                if field and value is not None:
                    where_clauses.append(f'"{field}" {operator} :{field}')
    
    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)
    
    # ORDER BY
    order_sql = f'ORDER BY "{sort_by}" {sort_order.upper()}'
    
    # LIMIT
    limit_sql = f"LIMIT {limit}"
    
    sql = f'SELECT {select_sql} FROM "{view_name}" {where_sql} {order_sql} {limit_sql}'
    
    try:
        # Execute with params
        exec_params = {}
        if filters:
            for f in filters:
                if isinstance(f, dict):
                    field = f.get("field", "")
                    value = f.get("value")
                    if field and value is not None:
                        exec_params[field] = value
        
        result_stmt = text(sql)
        result = await db.execute(result_stmt, exec_params)
        rows = result.fetchall()
        
        # Convert to dicts
        if rows and result.keys():
            data = [dict(zip(result.keys(), row)) for row in rows]
        else:
            data = []
        
        return {
            "report_id": report_id,
            "name": report.name,
            "columns": [r.keys() if hasattr(r, 'keys') else [] for r in data[:1]],
            "rows": data,
            "total_rows": len(data),
            "sql": sql
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report execution failed: {str(e)}")


@router.delete("/{report_id}")
async def delete_report_definition(
    report_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a report definition (admin only)."""
    stmt = select(ReportDefinition).where(ReportDefinition.id == report_id)
    result = await db.execute(stmt)
    report = result.scalar_one_or_none()
    
    if not report:
        raise HTTPException(status_code=404, detail="Report definition not found")
    
    await db.delete(report)
    await db.commit()
    
    return {"message": "Report definition deleted"}

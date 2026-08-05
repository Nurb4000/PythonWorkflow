"""
Shared query execution service for read-only operations.

Unifies the visual query and raw SQL execution paths used by
DatabaseQueryExecutor and ReportExecutor, eliminating duplication.

Write operations (INSERT/UPDATE/DELETE/UPSERT) remain in DatabaseQueryExecutor
as they cannot use the read-only visual builder.
"""
import logging
import re
from typing import Any, Dict, List, Optional

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def interpolate_value(value: Any, input_data: Dict[str, Any]) -> Any:
    """Recursively interpolate $input.* references in values."""
    if isinstance(value, str) and value.startswith("$input."):
        field = value[7:]
        return input_data.get(field, value)
    elif isinstance(value, dict):
        return {k: interpolate_value(v, input_data) for k, v in value.items()}
    elif isinstance(value, list):
        return [interpolate_value(item, input_data) for item in value]
    return value


def transform_visual_filters(
    raw_filters: List[Dict[str, Any]], input_data: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Transform QueryBuilder filter rows into data_query_service format with interpolation."""
    transformed = []
    for f in raw_filters:
        transformed.append({
            "field": f.get("column", ""),
            "operator": f.get("operator", "="),
            "value": interpolate_value(f.get("value", ""), input_data),
            "is_custom": f.get("mode") == "custom",
            "relationship_chain": f.get("rel_chain", []),
        })
    return transformed


DANGEROUS_KEYWORDS = [
    ";", "--", "/*", "*/",
    "DROP", "DELETE", "UPDATE", "INSERT",
    "ALTER", "CREATE", "TRUNCATE", "EXEC", "EXECUTE",
]


def validate_readonly_sql(sql: str) -> None:
    """Validate that SQL is a safe, read-only SELECT statement."""
    stripped = sql.strip()
    upper = stripped.upper().lstrip()

    if not upper.startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed")

    for keyword in DANGEROUS_KEYWORDS:
        if keyword == ";":
            if ";" in stripped:
                raise ValueError("Semicolons are not allowed in queries")
        elif keyword.startswith("--"):
            if keyword in stripped:
                raise ValueError("Comments are not allowed")
        else:
            pattern = r"\b" + keyword + r"\b"
            if re.search(pattern, stripped, re.IGNORECASE):
                raise ValueError(f"Query contains disallowed keyword: {keyword}")


def interpolate_sql(sql: str, input_data: Dict[str, Any]) -> str:
    """Replace $input.field references in raw SQL with actual values."""
    def replace_match(match):
        field = match.group(1)
        value = input_data.get(field, match.group(0))
        if isinstance(value, str):
            escaped = value.replace("'", "''")
            return "'" + escaped + "'"
        elif value is None:
            return "NULL"
        return str(value)
    return re.sub(r"\$input\.(\w+)", replace_match, sql)


async def execute_visual_query(
    db: AsyncSession,
    table_name: str,
    raw_filters: List[Dict[str, Any]],
    input_data: Dict[str, Any],
    logic: str = "AND",
    sort_by: Optional[str] = None,
    sort_order: str = "desc",
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    """Execute a visual query with $input.* interpolation.

    This is the shared entry point used by both DatabaseQueryExecutor and ReportExecutor.
    Delegates to data_query_service.execute_visual_query() after transforming filters.
    """
    from app.services.data_query_service import execute_visual_query as run_visual

    if not table_name:
        raise ValueError("Visual query requires a 'table'")

    transformed = transform_visual_filters(raw_filters, input_data) if raw_filters else []

    result = await run_visual(
        db,
        table_name=table_name,
        filters=transformed or None,
        logic=logic,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )

    return {
        "items": result.get("items", []),
        "total": result.get("total", 0),
        "limit": limit,
        "offset": offset,
    }


async def execute_raw_sql(
    db: AsyncSession,
    sql: str,
    input_data: Dict[str, Any],
    max_rows: int = 10000,
) -> Dict[str, Any]:
    """Execute a validated raw SQL query with $input.* interpolation.

    Shared entry point for read-only SQL execution used by both executors.
    """
    if not sql.strip():
        raise ValueError("SQL query is required")

    validate_readonly_sql(sql)
    interpolated = interpolate_sql(sql, input_data)

    result = await db.execute(sa_text(interpolated).limit(max_rows))

    columns = list(result.keys()) if result.returns_rows else []
    rows = []
    if result.returns_rows:
        for row in result.fetchall():
            rows.append(dict(zip(columns, row)))

    return {
        "columns": columns,
        "items": rows,
        "total": len(rows),
        "sql": interpolated,
    }

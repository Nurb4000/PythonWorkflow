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
        elif keyword in ("/*", "*/"):
            # Comment delimiters — use plain string search, not regex
            if keyword in stripped:
                raise ValueError(f"Query contains disallowed comment delimiter: {keyword}")
        else:
            pattern = r"\b" + re.escape(keyword) + r"\b"
            if re.search(pattern, stripped, re.IGNORECASE):
                raise ValueError(f"Query contains disallowed keyword: {keyword}")


def interpolate_sql(sql: str, input_data: Dict[str, Any]) -> tuple[str, dict]:
    """Replace $input.field references in raw SQL with positional placeholders.

    Returns (sql_with_placeholders, params_dict) where params_dict maps
    placeholder names ($1, $2, ...) to their resolved values.  This allows
    the database driver to handle proper escaping / type coercion instead of
    naive string concatenation.

    If a field is missing from input_data, the original ``$input.field`` token
    is left in place (the driver will raise at execution time).
    """
    params: dict[str, Any] = {}
    counter = 0

    def replace_match(match: re.Match) -> str:
        nonlocal counter
        field = match.group(1)
        value = input_data.get(field)  # None means "missing" — keep original token
        if value is None and field not in input_data:
            return match.group(0)  # leave $input.field as-is
        counter += 1
        placeholder = f"${counter}"
        params[placeholder] = value
        return placeholder

    new_sql = re.sub(r"\$input\.(\w+)", replace_match, sql)
    return new_sql, params


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
    """Execute a validated raw SQL query with $input.* parameterized substitution.

    Shared entry point for read-only SQL execution used by both executors.
    C3 fix: uses positional placeholders ($1, $2, ...) resolved by the driver
    instead of naive string interpolation.
    """
    if not sql.strip():
        raise ValueError("SQL query is required")

    validate_readonly_sql(sql)
    param_sql, params = interpolate_sql(sql, input_data)

    # Append LIMIT clause to the SQL string (sa_text doesn't have .limit())
    if max_rows > 0:
        # Check if the query already has a LIMIT clause
        upper_sql = param_sql.upper().strip()
        if not upper_sql.endswith((";",)):
            # Remove trailing semicolon if present
            clean_sql = param_sql.rstrip().rstrip(";")
            param_sql = f"{clean_sql} LIMIT {max_rows}"

    # Build bound parameters for SQLAlchemy text()
    bound = sa_text(param_sql)
    if params:
        bound = bound.bindparams(**params)

    result = await db.execute(bound)

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

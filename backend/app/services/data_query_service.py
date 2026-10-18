import csv
import io
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, Table, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import select, func

from app.models.auth import User, Group, AuditLog
from app.models.schemas import Workflow, WorkflowStep, WorkflowRun, StepInstance, Task, Schedule
from app.models.forms import Form, FormSubmission, FormTemplate
from app.models.custom_fields import CustomFieldDefinition
from app.models.email_trigger import EmailProcessingLog
from app.models.marketplace import MarketplaceItem, SavedNodeTemplate
from app.models.cmdb import CIType, ConfigurationItem, CIRelationship, CIHistory

logger = logging.getLogger(__name__)

# Registry of queryable tables: table_name -> (ORM model, display name)
QUERYABLE_TABLES: Dict[str, tuple] = {
    "tasks": (Task, "Tasks"),
    "workflow_runs": (WorkflowRun, "Workflow Runs"),
    "step_instances": (StepInstance, "Step Instances"),
    "users": (User, "Users"),
    "groups": (Group, "Groups"),
    "form_submissions": (FormSubmission, "Form Submissions"),
    "workflows": (Workflow, "Workflows"),
    "workflow_steps": (WorkflowStep, "Workflow Steps"),
    "forms": (Form, "Forms"),
    "schedules": (Schedule, "Schedules"),
    "ci_types": (CIType, "CI Types"),
    "configuration_items": (ConfigurationItem, "Configuration Items"),
    "ci_relationships": (CIRelationship, "CI Relationships"),
    "ci_history": (CIHistory, "CI History"),
    "audit_logs": (AuditLog, "Audit Logs"),
    "form_templates": (FormTemplate, "Form Templates"),
    "custom_field_definitions": (CustomFieldDefinition, "Custom Field Definitions"),
    "email_processing_log": (EmailProcessingLog, "Email Processing Log"),
    "marketplace_items": (MarketplaceItem, "Marketplace Items"),
    "saved_node_templates": (SavedNodeTemplate, "Saved Node Templates"),
}

# FK relationship map for chaining: (source_table, fk_column) -> (target_table, target_pk_column)
FK_MAP: List[tuple] = [
    ("tasks", "workflow_run_id", "workflow_runs", "id"),
    ("tasks", "step_id", "workflow_steps", "id"),
    ("tasks", "assigned_to_user_id", "users", "id"),
    ("tasks", "assigned_group_id", "groups", "id"),
    ("tasks", "form_id", "forms", "id"),
    ("workflow_runs", "workflow_id", "workflows", "id"),
    ("step_instances", "workflow_run_id", "workflow_runs", "id"),
    ("step_instances", "step_id", "workflow_steps", "id"),
    ("workflow_steps", "workflow_id", "workflows", "id"),
    ("form_submissions", "form_id", "forms", "id"),
    ("form_submissions", "submitted_by", "users", "id"),
    ("form_submissions", "workflow_run_id", "workflow_runs", "id"),
    ("schedules", "workflow_id", "workflows", "id"),
    ("configuration_items", "type_id", "ci_types", "id"),
    ("configuration_items", "created_by", "users", "id"),
    ("configuration_items", "updated_by", "users", "id"),
    ("ci_relationships", "source_ci_id", "configuration_items", "id"),
    ("ci_relationships", "target_ci_id", "configuration_items", "id"),
    ("ci_history", "ci_id", "configuration_items", "id"),
    ("ci_history", "changed_by", "users", "id"),
    ("audit_logs", "user_id", "users", "id"),
    ("custom_field_definitions", "created_by", "users", "id"),
    ("email_processing_log", "workflow_id", "workflows", "id"),
    ("email_processing_log", "run_id", "workflow_runs", "id"),
    ("marketplace_items", "author_id", "users", "id"),
    ("saved_node_templates", "user_id", "users", "id"),
    ("saved_node_templates", "source_marketplace_item_id", "marketplace_items", "id"),
]

# Build a lookup: (source_table, fk_column) -> (target_table, target_pk)
FK_LOOKUP: Dict[tuple, tuple] = {
    (src, fk): (tgt, tgt_pk) for src, fk, tgt, tgt_pk in FK_MAP
}

# Reverse lookup: (target_table, target_pk) -> list of (source_table, fk_column)
REVERSE_FK: Dict[tuple, List[tuple]] = {}
for src, fk, tgt, tgt_pk in FK_MAP:
    REVERSE_FK.setdefault((tgt, tgt_pk), []).append((src, fk))

ALLOWED_FIELD_TYPES = [
    "string", "number", "boolean", "date", "datetime", "text",
    "select", "email", "url", "currency", "relationship"
]


def get_native_columns(model: Any) -> List[Dict[str, str]]:
    """Return list of {name, type} for native columns on a model."""
    cols = []
    pk_cols = set(c.name for c in model.__table__.primary_key.columns)
    for col in model.__table__.columns:
        cols.append({
            "name": col.name,
            "type": str(col.type),
            "is_pk": col.primary_key or col.name in pk_cols,
        })
    return cols


def get_relationship_columns(table_name: str) -> List[Dict[str, Any]]:
    """Get available relationship columns for chaining from a given table."""
    rel_cols = []
    for (src, fk), (tgt, tgt_pk) in FK_LOOKUP.items():
        if src == table_name:
            target_model = QUERYABLE_TABLES.get(tgt, (None, None))[0]
            if target_model:
                target_native = get_native_columns(target_model)
                rel_cols.append({
                    "fk_column": fk,
                    "target_table": tgt,
                    "target_display": QUERYABLE_TABLES[tgt][1],
                    "available_columns": target_native,
                })
    return rel_cols


async def list_tables_with_fields(db: AsyncSession) -> List[Dict[str, Any]]:
    """List all queryable tables with their native columns and custom field definitions."""
    result = []
    for table_name, (model, display_name) in QUERYABLE_TABLES.items():
        errors = []
        try:
            native_cols = get_native_columns(model)
        except Exception as e:
            logger.error(f"Failed to get native columns for {table_name}: {e}")
            native_cols = []
            errors.append(f"native_columns: {e}")

        try:
            rel_cols = get_relationship_columns(table_name)
        except Exception as e:
            logger.error(f"Failed to get relationship columns for {table_name}: {e}")
            rel_cols = []
            errors.append(f"relationship_columns: {e}")

        # Get active custom fields for this table
        try:
            stmt = select(CustomFieldDefinition).where(
                CustomFieldDefinition.target_table == table_name,
                CustomFieldDefinition.is_active == True
            )
            cf_result = await db.execute(stmt)
            custom_fields = cf_result.scalars().all()
            cf_list = [
                {
                    "id": cf.id,
                    "field_key": cf.field_key,
                    "label": cf.label,
                    "field_type": cf.field_type,
                    "scope": cf.scope,
                    "scope_id": cf.scope_id,
                    "config": cf.config or {},
                }
                for cf in custom_fields
            ]
        except Exception as e:
            logger.error(f"Failed to get custom fields for {table_name}: {e}")
            cf_list = []
            errors.append(f"custom_fields: {e}")

        entry: Dict[str, Any] = {
            "table": table_name,
            "display_name": display_name,
            "native_columns": native_cols,
            "relationship_columns": rel_cols,
            "custom_fields": cf_list,
        }
        if errors:
            entry["error"] = "; ".join(errors)
        result.append(entry)
    return result


async def execute_visual_query(
    db: AsyncSession,
    table_name: str,
    filters: Optional[List[Dict[str, Any]]] = None,
    logic: str = "AND",
    sort_by: Optional[str] = None,
    sort_order: str = "asc",
    limit: int = 100,
    offset: int = 0,
    custom_field_scope_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Execute a visual filter query against a table.

    filters: list of {field, operator, value, is_custom, relationship_chain}
      - field: column name or custom field_key
      - operator: =, !=, >, <, >=, <=, contains, starts_with, ends_with, is_null, in
      - value: the filter value
      - is_custom: bool, True if filtering on a custom_data field
      - relationship_chain: list of {target_table, column} for chained lookups
    """
    if table_name not in QUERYABLE_TABLES:
        raise ValueError(f"Unknown table: {table_name}")

    model = QUERYABLE_TABLES[table_name][0]
    stmt = select(model)

    # Build filter conditions.
    # NOTE: values are bound via SQLAlchemy column operators (_apply_operator /
    # the _jsonb_* helpers), so there is no separate ``params`` dict here — do
    # not reintroduce a ``params``/``param_idx`` pair; it is dead code.
    conditions = []

    for f in (filters or []):
        field = f.get("field", "")
        operator = f.get("operator", "=")
        value = f.get("value")
        is_custom = f.get("is_custom", False)
        rel_chain = f.get("relationship_chain", [])

        if is_custom:
            # Filter on custom_data JSONB
            if operator == "is_null":
                conditions.append(_jsonb_key_is_null(model, field))
            elif operator == "=":
                conditions.append(_jsonb_eq(model, field, value))
            elif operator == "!=":
                conditions.append(_jsonb_neq(model, field, value))
            elif operator == "contains":
                conditions.append(_jsonb_contains(model, field, value))
            elif operator == "in":
                conditions.append(_jsonb_in(model, field, value if isinstance(value, list) else [value]))
            else:
                # For numeric operators on custom fields, cast to text comparison
                conditions.append(_jsonb_eq(model, field, value))
        elif rel_chain:
            # Relationship chain filter. ``_build_relationship_filter`` returns
            # None when the chain can't be resolved (unknown table/FK), so guard
            # with ``is not None`` — a SQLAlchemy clause can't be coerced to bool.
            cond = _build_relationship_filter(model, table_name, rel_chain, field, operator, value)
            if cond is not None:
                conditions.append(cond)
        else:
            # Native column filter
            col = getattr(model, field, None)
            if col is None:
                continue
            conditions.append(_apply_operator(col, operator, value))

    if conditions:
        if logic.upper() == "OR":
            stmt = stmt.where(sa_text(" OR ".join([str(c) for c in conditions])))
        else:
            stmt = stmt.where(*conditions)

    # Scope filter: if custom_field_scope_id is set, only include records where
    # the workflow-scoped custom fields match. This is handled at the field definition level.

    # Sorting
    if sort_by:
        col = getattr(model, sort_by, None)
        if col:
            stmt = stmt.order_by(col.desc() if sort_order == "desc" else col.asc())

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    count_result = await db.execute(count_stmt)
    total = count_result.scalar() or 0

    # Paginate
    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    # Serialize rows
    items = []
    for row in rows:
        item = {}
        for col in model.__table__.columns:
            val = getattr(row, col.name, None)
            if hasattr(val, 'isoformat'):
                val = val.isoformat()
            item[col.name] = val
        items.append(item)

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def _jsonb_key_is_null(model: Any, key: str):
    """Check if a JSONB key is null or missing."""
    data_col = model.custom_data
    return (data_col.is_(None)) | (sa_text(f"NOT {model.__tablename__}.custom_data ? :key").params(key=key))


def _jsonb_eq(model: Any, key: str, value: Any):
    """JSONB equality check."""
    if isinstance(value, bool):
        return model.custom_data[key].as_boolean() == value
    elif isinstance(value, (int, float)):
        return model.custom_data[key].as_float() == value
    else:
        return model.custom_data[key].as_string() == str(value)


def _jsonb_neq(model: Any, key: str, value: Any):
    if isinstance(value, bool):
        return model.custom_data[key].as_boolean() != value
    elif isinstance(value, (int, float)):
        return model.custom_data[key].as_float() != value
    else:
        return model.custom_data[key].as_string() != str(value)


def _jsonb_contains(model: Any, key: str, value: str):
    return model.custom_data[key].as_string().ilike(f"%{value}%")


def _jsonb_in(model: Any, key: str, values: list):
    return model.custom_data[key].as_string().in_([str(v) for v in values])


def _build_relationship_filter(
    base_model: Any, base_table: str, rel_chain: List[Dict[str, str]], field: str, operator: str, value: Any
):
    """Build a subquery filter for relationship chain lookups."""
    if not rel_chain:
        return None

    current_table = base_table
    current_model = base_model

    for rel in rel_chain[:-1]:
        target_table = rel["target_table"]
        fk_key = (current_table, rel.get("fk_column"))
        if fk_key not in FK_LOOKUP:
            return None
        tgt_table, tgt_pk = FK_LOOKUP[fk_key]
        tgt_model = QUERYABLE_TABLES.get(tgt_table, (None, None))[0]
        if not tgt_model:
            return None
        current_table = tgt_table
        current_model = tgt_model

    # Last hop
    last_rel = rel_chain[-1]
    target_table = last_rel["target_table"]
    fk_key = (current_table, last_rel.get("fk_column"))
    if fk_key not in FK_LOOKUP:
        return None
    tgt_table, tgt_pk = FK_LOOKUP[fk_key]
    tgt_model = QUERYABLE_TABLES.get(tgt_table, (None, None))[0]
    if not tgt_model:
        return None

    target_col = getattr(tgt_model, field, None)
    if not target_col:
        return None

    # Build subquery: SELECT id FROM target WHERE column operator value
    pk_col = getattr(base_model, "id", None)
    if not pk_col:
        return None

    # Walk the chain to build the join path
    sub_stmt = select(getattr(current_model, "id"))
    join_models = []

    # Build joins from base to current
    walk_table = base_table
    walk_model = base_model
    for rel in rel_chain:
        fk_key = (walk_table, rel.get("fk_column"))
        if fk_key not in FK_LOOKUP:
            return None
        tgt_t, tgt_p = FK_LOOKUP[fk_key]
        tgt_m = QUERYABLE_TABLES.get(tgt_t, (None, None))[0]
        if not tgt_m:
            return None
        sub_stmt = sub_stmt.join(tgt_m, getattr(walk_model, rel["fk_column"]) == tgt_m.id)
        walk_table = tgt_t
        walk_model = tgt_m

    # Now join to the final target for the filter
    final_fk_key = (walk_table, last_rel.get("fk_column"))
    if final_fk_key in FK_LOOKUP:
        final_tgt_t, _ = FK_LOOKUP[final_fk_key]
        final_tgt_m = QUERYABLE_TABLES.get(final_tgt_t, (None, None))[0]
        if final_tgt_m:
            sub_stmt = sub_stmt.join(final_tgt_m, getattr(walk_model, last_rel["fk_column"]) == final_tgt_m.id)
            filter_col = getattr(final_tgt_m, field, target_col)
        else:
            filter_col = target_col
    else:
        filter_col = target_col

    filter_cond = _apply_operator(filter_col, operator, value)
    sub_stmt = sub_stmt.where(filter_cond)

    return pk_col.in_(sub_stmt)


def _apply_operator(col, operator: str, value: Any):
    """Apply a comparison operator to a SQLAlchemy column."""
    if operator == "=":
        return col == value
    elif operator == "!=":
        return col != value
    elif operator == ">":
        return col > value
    elif operator == "<":
        return col < value
    elif operator == ">=":
        return col >= value
    elif operator == "<=":
        return col <= value
    elif operator == "contains":
        return col.ilike(f"%{value}%")
    elif operator == "starts_with":
        return col.ilike(f"{value}%")
    elif operator == "ends_with":
        return col.ilike(f"%{value}")
    elif operator == "is_null":
        if value:
            return col.isnot(None)
        else:
            return col.is_(None)
    elif operator == "in":
        vals = value if isinstance(value, list) else [value]
        return col.in_(vals)
    else:
        return col == value


async def execute_sql_query(db: AsyncSession, sql: str, max_rows: int = 10000) -> Dict[str, Any]:
    """Execute a read-only SQL query with safety checks."""
    sql_stripped = sql.strip()

    # Safety: only allow SELECT statements
    upper = sql_stripped.upper().lstrip()
    if not upper.startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed")

    # Safety: reject dangerous patterns
    dangerous = [";", "--", "/*", "*/", "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "TRUNCATE"]
    for word in dangerous:
        # Check word boundaries to avoid false positives on column names
        if word == ";":
            # Allow semicolons only at end or followed by whitespace/comments
            if ";" in sql_stripped:
                raise ValueError("Semicolons are not allowed in queries")
        elif word.startswith("--"):
            if word in sql_stripped:
                raise ValueError(f"Comments are not allowed")
        else:
            # Check for SQL keywords that aren't part of SELECT
            pattern = r'\b' + word + r'\b'
            import re
            if re.search(pattern, sql_stripped, re.IGNORECASE) and word not in ("SELECT",):
                raise ValueError(f"Query contains disallowed keyword: {word}")

    # Execute with row limit safety net
    try:
        result = await db.execute(sa_text(sql).limit(max_rows))
    except Exception as e:
        # If LIMIT isn't supported on the raw text, wrap in subquery
        wrapped = f"SELECT * FROM ({sql_stripped}) AS limited_subq LIMIT {max_rows}"
        result = await db.execute(sa_text(wrapped))

    rows = []
    if result.returns_rows:
        columns = list(result.keys())
        for row in result.fetchall():
            rows.append(dict(zip(columns, row)))

    return {
        "columns": list(result.keys()) if result.returns_rows else [],
        "items": rows,
        "total": len(rows),
    }


async def export_table_to_csv(
    db: AsyncSession,
    table_name: str,
    columns: Optional[List[str]] = None,
    limit: int = 10000,
) -> str:
    """Export a table to CSV string."""
    if table_name not in QUERYABLE_TABLES:
        raise ValueError(f"Unknown table: {table_name}")

    model = QUERYABLE_TABLES[table_name][0]
    all_cols = [c.name for c in model.__table__.columns]
    export_cols = columns or all_cols
    export_cols = [c for c in export_cols if c in all_cols]

    stmt = select(model).limit(limit)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(export_cols)

    for row in rows:
        writer.writerow([
            row.__getattribute__(c).isoformat() if hasattr(row.__getattribute__(c), 'isoformat')
            else row.__getattribute__(c)
            for c in export_cols
        ])

    return output.getvalue()


async def export_query_to_csv(
    db: AsyncSession,
    table_name: str,
    filters: Optional[List[Dict[str, Any]]] = None,
    logic: str = "AND",
    sort_by: Optional[str] = None,
    sort_order: str = "asc",
    limit: int = 10000,
) -> str:
    """Execute a visual query and export results to CSV."""
    result = await execute_visual_query(
        db, table_name, filters, logic, sort_by, sort_order, limit, 0
    )

    if not result["items"]:
        return ""

    columns = list(result["items"][0].keys())
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)

    for item in result["items"]:
        writer.writerow([
            val.isoformat() if hasattr(val, 'isoformat') else val
            for val in item.values()
        ])

    return output.getvalue()


async def update_custom_data(
    db: AsyncSession,
    table_name: str,
    record_id: int,
    field_key: str,
    value: Any,
) -> bool:
    """Update a custom_data field on a specific record."""
    if table_name not in QUERYABLE_TABLES:
        raise ValueError(f"Unknown table: {table_name}")

    model = QUERYABLE_TABLES[table_name][0]
    stmt = select(model).where(model.id == record_id)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if not record:
        return False

    current = record.custom_data or {}
    current[field_key] = value
    record.custom_data = current

    await db.commit()
    await db.refresh(record)
    return True


async def bulk_update_custom_data(
    db: AsyncSession,
    table_name: str,
    record_ids: List[int],
    field_key: str,
    value: Any,
) -> int:
    """Bulk update a custom_data field on multiple records. Returns count updated."""
    if table_name not in QUERYABLE_TABLES:
        raise ValueError(f"Unknown table: {table_name}")

    model = QUERYABLE_TABLES[table_name][0]
    stmt = select(model).where(model.id.in_(record_ids))
    result = await db.execute(stmt)
    records = result.scalars().all()

    count = 0
    for record in records:
        current = record.custom_data or {}
        current[field_key] = value
        record.custom_data = current
        count += 1

    if count > 0:
        await db.commit()

    return count


async def log_custom_field_audit(
    db: AsyncSession,
    user_id: int,
    action: str,
    resource_type: str,
    resource_id: Optional[int],
    details: str,
):
    """Log a custom field change to the audit log."""
    from app.models.auth import AuditLog
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
    )
    db.add(entry)
    await db.commit()

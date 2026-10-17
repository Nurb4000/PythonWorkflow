"""
F1: Auto-generate per-form SQL VIEWs for structured reporting.

Generates read-only views that materialize form submissions and CI items as
flat typed tables. Naming: v_form_<key>, v_ci_<key>. Regenerated on publish.
Uses jsonb_to_record for JSONB extraction.
"""
import logging
import re
from typing import Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)

# M10 fix: SQL identifiers (column names, view names, JSONB path keys) cannot be
# parameterized, so they must be validated against a strict allowlist before being
# interpolated into DDL/DML. Only ASCII letters, digits and underscores are
# permitted, and the identifier must not start with a digit.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def is_valid_identifier(name: Any) -> bool:
    """Return True if *name* is a safe SQL identifier (no injection possible)."""
    return isinstance(name, str) and bool(_IDENTIFIER_RE.match(name))


class SqlViewService:
    """Manage auto-generated SQL VIEWs for forms and CI types."""
    
    async def ensure_form_view(self, db: AsyncSession, form_id: int, form_key: str) -> Dict[str, Any]:
        """Ensure a SQL VIEW exists for a form's submissions."""
        # Get form schema to determine columns
        from app.models.forms import Form
        stmt = text("SELECT id, name, schema_json FROM forms WHERE id = :id")
        result = await db.execute(stmt, {"id": form_id})
        row = result.fetchone()
        
        if not row:
            return {"success": False, "error": f"Form {form_id} not found"}
        
        schema = row.schema_json or {}
        properties = schema.get("properties", {})
        
        if not properties:
            return {"success": True, "message": "No properties to create view for"}
        
        # M10: form_key is interpolated into the view name (an identifier), so it
        # must be a valid identifier too.
        if not is_valid_identifier(form_key):
            return {"success": False, "error": f"Invalid form_key: {form_key!r}"}

        # Build column definitions
        columns = []
        for field_name, field_def in properties.items():
            if not is_valid_identifier(field_name):
                logger.warning(
                    "Skipping form field %r: not a valid SQL identifier", field_name
                )
                continue
            if isinstance(field_def, dict):
                field_type = field_def.get("type", "text")
                sql_type = self._map_json_schema_type(field_type)
                columns.append(f'"{field_name}" {sql_type}')
        
        if not columns:
            return {"success": True, "message": "No valid columns in schema"}
        
        # Generate CREATE OR REPLACE VIEW SQL
        view_name = f"v_form_{form_key}"
        cols_sql = ", ".join(columns)
        
        # Extract data from JSONB submissions
        select_cols = []
        for field_name in properties.keys():
            if not is_valid_identifier(field_name):
                continue
            select_cols.append(f'jsonb_extract_path_text(data, \'{field_name}\') as "{field_name}"')
        
        select_sql = ", ".join(select_cols) if select_cols else "'unknown' as _placeholder"
        
        sql = f"""
        CREATE OR REPLACE VIEW {view_name} AS
        SELECT 
            fs.id as submission_id,
            fs.form_id,
            fs.submitted_by,
            fs.submitted_at,
            {select_sql}
        FROM form_submissions fs
        WHERE fs.form_id = {form_id}
        """
        
        try:
            await db.execute(text(sql))
            await db.commit()
            return {"success": True, "view_name": view_name, "columns": columns}
        except Exception as e:
            await db.rollback()
            return {"success": False, "error": str(e), "sql": sql}
    
    async def ensure_ci_type_view(self, db: AsyncSession, ci_type_id: int, ci_type_key: str) -> Dict[str, Any]:
        """Ensure a SQL VIEW exists for a CI type's items."""
        from app.models.cmdb import CIType
        stmt = text("SELECT id, key, field_schema FROM ci_types WHERE id = :id")
        result = await db.execute(stmt, {"id": ci_type_id})
        row = result.fetchone()
        
        if not row:
            return {"success": False, "error": f"CI type {ci_type_id} not found"}
        
        field_schema = row.field_schema or []

        # M10: ci_type_key is interpolated into the view name (an identifier).
        if not is_valid_identifier(ci_type_key):
            return {"success": False, "error": f"Invalid ci_type_key: {ci_type_key!r}"}

        columns = []
        select_cols = []

        for field in field_schema:
            if isinstance(field, dict) and "key" in field:
                field_key = field["key"]
                if not is_valid_identifier(field_key):
                    logger.warning(
                        "Skipping CI type field %r: not a valid SQL identifier", field_key
                    )
                    continue
                field_type = field.get("type", "text")
                sql_type = self._map_json_schema_type(field_type)
                columns.append(f'"{field_key}" {sql_type}')
                select_cols.append(f'jsonb_extract_path_text(ci_data, \'{field_key}\') as "{field_key}"')

        if not select_cols:
            return {"success": True, "message": "No valid fields in schema"}

        select_sql = ", ".join(select_cols)
        view_name = f"v_ci_{ci_type_key}"
        
        sql = f"""
        CREATE OR REPLACE VIEW {view_name} AS
        SELECT 
            ci.id as item_id,
            ci.type_id,
            ci.name,
            ci.status,
            {select_sql}
        FROM configuration_items ci
        WHERE ci.type_id = {ci_type_id}
          AND ci.is_active = true
        """
        
        try:
            await db.execute(text(sql))
            await db.commit()
            return {"success": True, "view_name": view_name, "columns": columns}
        except Exception as e:
            await db.rollback()
            return {"success": False, "error": str(e), "sql": sql}
    
    def _map_json_schema_type(self, json_type: str) -> str:
        """Map JSON Schema types to PostgreSQL types."""
        type_map = {
            "string": "text",
            "text": "text",
            "number": "numeric",
            "integer": "bigint",
            "boolean": "boolean",
            "date": "date",
            "datetime": "timestamptz",
            "email": "text",
            "url": "text",
            "currency": "numeric",
        }
        return type_map.get(json_type, "text")
    
    async def drop_view(self, db: AsyncSession, view_name: str) -> Dict[str, Any]:
        """Drop a generated view."""
        # M10: view_name is interpolated into DDL as an identifier. Generated views
        # are always v_form_<key>/v_ci_<key> with a validated <key>, so reject any
        # caller-supplied name that is not itself a valid identifier.
        if not is_valid_identifier(view_name):
            return {"success": False, "error": f"Invalid view_name: {view_name!r}"}
        try:
            await db.execute(text(f'DROP VIEW IF EXISTS "{view_name}"'))
            await db.commit()
            return {"success": True, "message": f"View {view_name} dropped"}
        except Exception as e:
            await db.rollback()
            return {"success": False, "error": str(e)}
    
    async def list_views(self, db: AsyncSession) -> List[Dict[str, Any]]:
        """List all generated views."""
        stmt = text("""
            SELECT 
                schemaname,
                viewname,
                definition
            FROM pg_views 
            WHERE schemaname = 'public'
              AND viewname LIKE 'v_form_%'
              OR viewname LIKE 'v_ci_%'
            ORDER BY viewname
        """)
        result = await db.execute(stmt)
        rows = result.fetchall()
        
        return [
            {
                "schema": row.schemaname,
                "name": row.viewname,
                "preview": (row.definition or "")[:200] + "..." if len(row.definition or "") > 200 else row.definition
            }
            for row in rows
        ]

    async def sync_views(self, db: AsyncSession) -> None:
        """Re-create all active SQL views from their stored definitions.

        Run on startup so views that were dropped at the database level (e.g.
        after a manual ``DROP VIEW`` or a rolled-back migration) are rebuilt from
        the ``definition_sql`` persisted in the ``sql_views`` table.
        """
        from sqlalchemy import select
        from app.models.sql_views import SQLView

        stmt = select(SQLView).where(SQLView.is_active.is_(True))
        result = await db.execute(stmt)
        views = result.scalars().all()

        for view in views:
            try:
                await db.execute(text(view.definition_sql))
                logger.info(f"Synced SQL view: {view.name}")
            except Exception as e:
                logger.warning(f"Failed to sync SQL view {view.name}: {e}")

        await db.commit()


sql_view_service = SqlViewService()

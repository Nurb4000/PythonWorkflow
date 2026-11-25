"""
C2: Field library resolution — resolve $ref: field:<key> in schemas.

Forms and CI types can reference shared field definitions via:
  {"$ref": "field:cost_center"}

This resolves to the full field definition at render/validation time.
Inline definitions (without $ref) remain valid forever for backward compat.
"""
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.field_library import FieldDefinition


async def resolve_field_ref(db: AsyncSession, ref: str) -> Optional[Dict[str, Any]]:
    """Resolve a $ref to a field definition.
    
    Args:
        ref: "$ref" value, expected format "field:<key>"
    
    Returns:
        Field definition dict or None if not found.
    """
    if not ref.startswith("field:"):
        return None
    
    key = ref[6:]  # Strip "field:"
    stmt = select(FieldDefinition).where(
        FieldDefinition.key == key,
        FieldDefinition.is_active == True,
        FieldDefinition.is_deprecated == False
    )
    result = await db.execute(stmt)
    field = result.scalar_one_or_none()
    
    if not field:
        return None
    
    return {
        "id": field.id,
        "key": field.key,
        "label": field.label,
        "type": field.field_type,
        "options": field.options or [],
        "validation": field.validation_rules or {},
        "help_text": field.help_text,
        "description": field.description,
    }


def resolve_schema_refs(schema: Dict[str, Any], field_defs: Dict[str, Dict]) -> Dict[str, Any]:
    """Recursively resolve $ref in a JSON schema.
    
    Args:
        schema: JSON Schema (possibly with $ref entries)
        field_defs: Cache of resolved field definitions {key: definition}
    
    Returns:
        Resolved schema with $ref replaced by inline field definitions.
    """
    if isinstance(schema, dict):
        if "$ref" in schema:
            ref = schema["$ref"]
            if ref.startswith("field:"):
                key = ref[6:]
                if key in field_defs:
                    # Replace $ref with inline definition
                    resolved = dict(field_defs[key])
                    resolved.pop("id", None)  # Don't expose internal ID
                    return resolved
            return {"$ref": ref}  # Unknown ref, keep as-is
        return {k: resolve_schema_refs(v, field_defs) for k, v in schema.items()}
    elif isinstance(schema, list):
        return [resolve_schema_refs(item, field_defs) for item in schema]
    return schema


async def get_field_definitions_map(db: AsyncSession, keys: List[str]) -> Dict[str, Dict]:
    """Fetch multiple field definitions by key.
    
    Args:
        db: Database session
        keys: List of field keys
    
    Returns:
        Dict mapping key -> resolved field definition
    """
    if not keys:
        return {}
    
    stmt = select(FieldDefinition).where(
        FieldDefinition.key.in_(keys),
        FieldDefinition.is_active == True,
        FieldDefinition.is_deprecated == False
    )
    result = await db.execute(stmt)
    fields = result.scalars().all()
    
    return {
        f.key: {
            "key": f.key,
            "label": f.label,
            "type": f.field_type,
            "options": f.options or [],
            "validation": f.validation_rules or {},
            "help_text": f.help_text,
            "description": f.description,
        }
        for f in fields
    }

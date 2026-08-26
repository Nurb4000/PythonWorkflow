"""
Where-used scanning service — finds all references to a field definition.
"""
import json
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

logger = logging.getLogger(__name__)


class WhereUsedService:
    """Scan forms and CI types for field library references."""
    
    async def find_form_references(
        self, 
        db: AsyncSession, 
        field_key: str
    ) -> List[Dict[str, Any]]:
        """Find all forms that reference a field definition."""
        from app.models.forms import Form
        
        stmt = select(Form).where(Form.is_active == True)
        result = await db.execute(stmt)
        forms = result.scalars().all()
        
        references = []
        for form in forms:
            if not form.schema_json:
                continue
            
            schema = form.schema_json
            if isinstance(schema, str):
                try:
                    schema = json.loads(schema)
                except json.JSONDecodeError:
                    continue
            
            properties = schema.get("properties", {})
            for prop_name, prop_def in properties.items():
                if isinstance(prop_def, dict) and prop_def.get("field_def_id"):
                    # Check if this references the field
                    if str(prop_def["field_def_id"]) == field_key or prop_def.get("key") == field_key:
                        references.append({
                            "type": "form",
                            "id": form.id,
                            "name": form.name,
                            "field_name": prop_name,
                            "reference_type": "field_def_id" if "field_def_id" in prop_def else "key"
                        })
        
        return references
    
    async def find_ci_type_references(
        self, 
        db: AsyncSession, 
        field_key: str
    ) -> List[Dict[str, Any]]:
        """Find all CI types that reference a field definition."""
        from app.models.cmdb import CIType
        
        stmt = select(CIType).where(CIType.is_active == True)
        result = await db.execute(stmt)
        ci_types = result.scalars().all()
        
        references = []
        for ci_type in ci_types:
            if not ci_type.field_schema:
                continue
            
            field_schema = ci_type.field_schema
            if isinstance(field_schema, str):
                try:
                    field_schema = json.loads(field_schema)
                except json.JSONDecodeError:
                    continue
            
            for field in field_schema:
                if isinstance(field, dict) and field.get("field_def_id"):
                    if str(field["field_def_id"]) == field_key or field.get("key") == field_key:
                        references.append({
                            "type": "ci_type",
                            "id": ci_type.id,
                            "name": ci_type.name,
                            "field_key": field.get("key", ""),
                            "reference_type": "field_def_id" if "field_def_id" in field else "key"
                        })
        
        return references
    
    async def find_all_references(
        self, 
        db: AsyncSession, 
        field_id: int
    ) -> Dict[str, Any]:
        """Find all references to a field definition across the system."""
        form_refs = await self.find_form_references(db, str(field_id))
        ci_refs = await self.find_ci_type_references(db, str(field_id))
        
        return {
            "field_id": field_id,
            "forms": form_refs,
            "ci_types": ci_refs,
            "total_references": len(form_refs) + len(ci_refs)
        }


where_used_service = WhereUsedService()

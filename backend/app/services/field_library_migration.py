"""
Field Library Migration Service — helps migrate inline fields to library references.
"""
import json
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger(__name__)


class FieldLibraryMigrationService:
    """Scan for inline fields and suggest migration to library."""
    
    async def scan_forms(
        self, 
        db: AsyncSession,
        min_uses: int = 2
    ) -> List[Dict[str, Any]]:
        """Scan forms for fields that could be promoted to library."""
        from app.models.forms import Form
        
        stmt = select(Form).where(Form.is_active == True)
        result = await db.execute(stmt)
        forms = result.scalars().all()
        
        field_usage: Dict[str, Dict[str, Any]] = {}
        
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
            for field_name, field_def in properties.items():
                if not isinstance(field_def, dict):
                    continue
                
                # Skip if already a library reference
                if field_def.get("field_def_id"):
                    continue
                
                # Track field usage
                key = f"{field_name}:{field_def.get('type', 'string')}"
                if key not in field_usage:
                    field_usage[key] = {
                        "field_name": field_name,
                        "type": field_def.get("type", "string"),
                        "forms": [],
                        "count": 0
                    }
                
                field_usage[key]["forms"].append({
                    "form_id": form.id,
                    "form_name": form.name
                })
                field_usage[key]["count"] += 1
        
        # Filter by min_uses
        candidates = [
            usage for usage in field_usage.values() 
            if usage["count"] >= min_uses
        ]
        
        return sorted(candidates, key=lambda x: x["count"], reverse=True)
    
    async def scan_ci_types(
        self, 
        db: AsyncSession,
        min_uses: int = 2
    ) -> List[Dict[str, Any]]:
        """Scan CI types for fields that could be promoted to library."""
        from app.models.cmdb import CIType
        
        stmt = select(CIType).where(CIType.is_active == True)
        result = await db.execute(stmt)
        ci_types = result.scalars().all()
        
        field_usage: Dict[str, Dict[str, Any]] = {}
        
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
                if not isinstance(field, dict):
                    continue
                
                # Skip if already a library reference
                if field.get("field_def_id"):
                    continue
                
                key = f"{field.get('key', '')}:{field.get('type', 'string')}"
                if key not in field_usage:
                    field_usage[key] = {
                        "field_key": field.get("key", ""),
                        "type": field.get("type", "string"),
                        "ci_types": [],
                        "count": 0
                    }
                
                field_usage[key]["ci_types"].append({
                    "ci_type_id": ci_type.id,
                    "ci_type_name": ci_type.name
                })
                field_usage[key]["count"] += 1
        
        # Filter by min_uses
        candidates = [
            usage for usage in field_usage.values() 
            if usage["count"] >= min_uses
        ]
        
        return sorted(candidates, key=lambda x: x["count"], reverse=True)
    
    async def generate_migration_plan(
        self,
        db: AsyncSession,
        forms_candidates: List[Dict],
        ci_candidates: List[Dict]
    ) -> Dict[str, Any]:
        """Generate a migration plan from scan results."""
        return {
            "forms": {
                "total_forms_scanned": len(forms_candidates),
                "candidates": forms_candidates
            },
            "ci_types": {
                "total_ci_types_scanned": len(ci_candidates),
                "candidates": ci_candidates
            },
            "summary": {
                "total_candidates": len(forms_candidates) + len(ci_candidates),
                "recommendation": "Review candidates and promote to field library"
            }
        }


field_library_migration_service = FieldLibraryMigrationService()

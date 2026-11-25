"""
Lookup service for form fields — searches users, CI items, or custom sources.
"""
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

logger = logging.getLogger(__name__)


class LookupService:
    """Service for performing lookups against various data sources."""
    
    async def lookup_users(
        self, 
        db: AsyncSession, 
        search_field: str, 
        search_value: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search users by field."""
        from app.models.auth import User
        
        # Map search_field to actual column
        field_map = {
            'username': User.username,
            'email': User.email,
            'full_name': User.full_name,
            'id': User.id,
        }
        
        column = field_map.get(search_field)
        if not column:
            return []
        
        stmt = select(User).where(
            or_(
                column.ilike(f"%{search_value}%"),
                User.username.ilike(f"%{search_value}%")
            )
        ).limit(limit)
        
        result = await db.execute(stmt)
        users = result.scalars().all()
        
        return [
            {
                'id': u.id,
                'username': u.username,
                'email': u.email,
                'full_name': u.full_name,
                'role': u.role,
            }
            for u in users
        ]
    
    async def lookup_ci_items(
        self, 
        db: AsyncSession, 
        type_key: str,
        search_field: str, 
        search_value: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search CI items by field."""
        from app.models.cmdb import ConfigurationItem, CIType
        
        # Get CI type
        type_stmt = select(CIType).where(CIType.key == type_key, CIType.is_active == True)
        type_result = await db.execute(type_stmt)
        ci_type = type_result.scalar_one_or_none()
        
        if not ci_type:
            return []
        
        # Search in ci_data JSONB
        stmt = select(ConfigurationItem).where(
            ConfigurationItem.type_id == ci_type.id,
            ConfigurationItem.is_active == True,
            ConfigurationItem.ci_data[search_field].astext.ilike(f"%{search_value}%")
        ).limit(limit)
        
        result = await db.execute(stmt)
        items = result.scalars().all()
        
        return [
            {
                'id': item.id,
                'name': item.name,
                'type_id': item.type_id,
                'ci_data': item.ci_data or {},
            }
            for item in items
        ]
    
    async def perform_lookup(
        self, 
        db: AsyncSession, 
        lookup_config: Dict[str, Any],
        search_value: str
    ) -> Optional[Dict[str, Any]]:
        """Perform a lookup based on configuration."""
        target_type = lookup_config.get('target_type', 'users')
        search_field = lookup_config.get('search_field', 'username')
        
        if target_type == 'users':
            results = await self.lookup_users(db, search_field, search_value)
            return results[0] if results else None
        
        elif target_type == 'ci_items':
            type_key = lookup_config.get('ci_type_key', '')
            if not type_key:
                return None
            results = await self.lookup_ci_items(db, type_key, search_field, search_value)
            return results[0] if results else None
        
        return None
    
    async def extract_result_fields(
        self, 
        lookup_result: Dict[str, Any], 
        result_fields: List[str]
    ) -> Dict[str, Any]:
        """Extract specific fields from lookup result."""
        if not lookup_result:
            return {}
        
        extracted = {}
        for field in result_fields:
            if field in lookup_result:
                extracted[field] = lookup_result[field]
            elif 'ci_data' in lookup_result and field in lookup_result['ci_data']:
                extracted[field] = lookup_result['ci_data'][field]
        
        return extracted


# Singleton instance
lookup_service = LookupService()

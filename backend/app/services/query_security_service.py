"""
Query security service — filters queries based on role permissions.
"""
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

logger = logging.getLogger(__name__)


class QuerySecurityService:
    """Enforce table/field-level security on queries."""
    
    async def filter_query_results(
        self,
        db: AsyncSession,
        user,
        table_name: str,
        results: List[Dict],
        action: str = "view"
    ) -> List[Dict]:
        """Filter query results based on user's visible fields."""
        from app.models.role_permissions import role_permission_service
        
        # Get visible fields for this user/table
        visible_fields = await role_permission_service.get_visible_fields(
            db, user, table_name
        )
        
        if not visible_fields or visible_fields == ["*"]:
            # No restrictions or all fields visible
            return results
        
        # Filter each row to only include visible fields
        filtered = []
        for row in results:
            filtered_row = {}
            for field in visible_fields:
                if field in row:
                    filtered_row[field] = row[field]
            filtered.append(filtered_row)
        
        return filtered
    
    async def validate_query_access(
        self,
        db: AsyncSession,
        user,
        table_name: str,
        action: str = "view"
    ) -> bool:
        """Check if user has access to a table for the given action."""
        from app.models.role_permissions import role_permission_service
        
        return await role_permission_service.can_user_access_table(
            db, user, table_name, action
        )
    
    async def get_allowed_tables(
        self,
        db: AsyncSession,
        user
    ) -> List[str]:
        """Get list of tables user has view access to."""
        from app.models.role_permissions import RolePermission
        from sqlalchemy import select
        
        # Get all permissions for user's roles
        stmt = select(RolePermission.table_name).where(
            RolePermission.role_id.in_([r.id for r in user.roles]) if user.roles else [],
            RolePermission.can_view == True,
            RolePermission.is_active == True
        )
        result = await db.execute(stmt)
        tables = result.scalars().all()
        
        return list(set(tables)) if tables else []


query_security_service = QuerySecurityService()

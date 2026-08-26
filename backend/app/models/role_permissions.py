"""
Role permissions model for table/field-level security.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, ForeignKey, func
from app.core.database import Base


class RolePermission(Base):
    """Defines what tables and fields a role can access."""
    __tablename__ = "role_permissions"

    id = Column(Integer, primary_key=True, index=True)
    role_id = Column(Integer, ForeignKey("custom_roles.id"), nullable=False)
    
    # Table-level permissions
    table_name = Column(String(100), nullable=False)  # e.g., "workflows", "configuration_items"
    can_view = Column(Boolean, default=True)
    can_edit = Column(Boolean, default=False)
    can_delete = Column(Boolean, default=False)
    
    # Field-level permissions (JSON array of field names or "*")
    visible_fields = Column(JSON, default=list)  # Fields user can see
    editable_fields = Column(JSON, default=list)  # Fields user can edit
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "role_id": self.role_id,
            "table_name": self.table_name,
            "can_view": self.can_view,
            "can_edit": self.can_edit,
            "can_delete": self.can_delete,
            "visible_fields": self.visible_fields or [],
            "editable_fields": self.editable_fields or [],
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class RolePermissionService:
    """Service for checking role permissions."""
    
    @staticmethod
    async def can_user_access_table(db, user, table_name: str, action: str = "view") -> bool:
        """Check if user has permission to access a table."""
        from sqlalchemy import select
        
        # Get user's roles
        stmt = select(RolePermission).where(
            RolePermission.role_id.in_([r.id for r in user.roles]) if user.roles else [],
            RolePermission.table_name == table_name,
            RolePermission.is_active == True
        )
        result = await db.execute(stmt)
        permissions = result.scalars().all()
        
        if not permissions:
            # No explicit permission = deny by default
            return False
        
        # Check if any role grants the action
        for perm in permissions:
            if action == "view" and perm.can_view:
                return True
            elif action == "edit" and perm.can_edit:
                return True
            elif action == "delete" and perm.can_delete:
                return True
        
        return False
    
    @staticmethod
    async def get_visible_fields(db, user, table_name: str) -> list:
        """Get fields visible to user for a table."""
        from sqlalchemy import select
        
        stmt = select(RolePermission).where(
            RolePermission.role_id.in_([r.id for r in user.roles]) if user.roles else [],
            RolePermission.table_name == table_name,
            RolePermission.is_active == True
        )
        result = await db.execute(stmt)
        permissions = result.scalars().all()
        
        if not permissions:
            return []
        
        # Merge visible fields from all matching permissions
        visible = set()
        for perm in permissions:
            if perm.visible_fields:
                if "*" in perm.visible_fields:
                    return ["*"]  # All fields visible
                visible.update(perm.visible_fields)
        
        return list(visible) if visible else []
    
    @staticmethod
    async def get_editable_fields(db, user, table_name: str) -> list:
        """Get fields editable by user for a table."""
        from sqlalchemy import select
        
        stmt = select(RolePermission).where(
            RolePermission.role_id.in_([r.id for r in user.roles]) if user.roles else [],
            RolePermission.table_name == table_name,
            RolePermission.is_active == True
        )
        result = await db.execute(stmt)
        permissions = result.scalars().all()
        
        if not permissions:
            return []
        
        editable = set()
        for perm in permissions:
            if perm.editable_fields:
                if "*" in perm.editable_fields:
                    return ["*"]  # All fields editable
                editable.update(perm.editable_fields)
        
        return list(editable) if editable else []


role_permission_service = RolePermissionService()

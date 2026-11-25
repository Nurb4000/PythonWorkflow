"""
Audit trail service — detailed change history for all objects.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

logger = logging.getLogger(__name__)


class AuditEntry:
    """Represents a single audit log entry."""
    
    def __init__(self, id: int, entity_type: str, entity_id: int, 
                 action: str, user_id: Optional[int], user_name: str,
                 changes: Dict[str, Any], timestamp: datetime):
        self.id = id
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.action = action  # create, update, delete, status_change
        self.user_id = user_id
        self.user_name = user_name
        self.changes = changes  # {field: {old: ..., new: ...}}
        self.timestamp = timestamp
    
    def to_dict(self):
        return {
            "id": self.id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "action": self.action,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "changes": self.changes,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }


class AuditService:
    """Service for recording and retrieving audit trail entries."""
    
    async def log_change(
        self,
        db: AsyncSession,
        entity_type: str,
        entity_id: int,
        action: str,
        user_id: Optional[int],
        user_name: str,
        changes: Dict[str, Any],
        old_values: Optional[Dict] = None,
        new_values: Optional[Dict] = None
    ):
        """Record a change in the audit log."""
        from app.models.audit_log import AuditLog
        
        audit_entry = AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            user_id=user_id,
            user_name=user_name,
            changes=json.dumps(changes) if changes else None,
            old_values=json.dumps(old_values) if old_values else None,
            new_values=json.dumps(new_values) if new_values else None,
            timestamp=datetime.now(timezone.utc)
        )
        
        db.add(audit_entry)
        await db.commit()
        logger.info(f"Audit: {action} {entity_type}#{entity_id} by {user_name}")
    
    async def get_audit_trail(
        self,
        db: AsyncSession,
        entity_type: str,
        entity_id: Optional[int] = None,
        user_id: Optional[int] = None,
        limit: int = 100
    ) -> List[AuditEntry]:
        """Get audit trail for an entity."""
        from app.models.audit_log import AuditLog
        
        stmt = select(AuditLog).where(AuditLog.entity_type == entity_type)
        
        if entity_id:
            stmt = stmt.where(AuditLog.entity_id == entity_id)
        if user_id:
            stmt = stmt.where(AuditLog.user_id == user_id)
        
        stmt = stmt.order_by(AuditLog.timestamp.desc()).limit(limit)
        result = await db.execute(stmt)
        logs = result.scalars().all()
        
        return [
            AuditEntry(
                id=log.id,
                entity_type=log.entity_type,
                entity_id=log.entity_id,
                action=log.action,
                user_id=log.user_id,
                user_name=log.user_name or "",
                changes=json.loads(log.changes) if log.changes else {},
                timestamp=log.timestamp
            )
            for log in logs
        ]


audit_service = AuditService()

"""Helpers for creating and querying in-app notifications (Feature-Plan §2.3).

A notification is a single-user, read/unread-tracked message about an event that
matters to that user (task assignment, SLA breach, workflow completion/failure,
...). Creation flushes rather than commits so the row is owned by the caller's
transaction -- e.g. a task-assignment notification commits alongside the task it
describes and rolls back with it.
"""
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import Notification


async def create_notification(
    db: AsyncSession,
    user_id: int,
    title: str,
    message: str = "",
    type: str = "info",
    related_entity_type: Optional[str] = None,
    related_entity_id: Optional[int] = None,
) -> Notification:
    """Create and flush a notification for ``user_id`` in the current transaction."""
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=type,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
    )
    db.add(notification)
    await db.flush()
    return notification


async def unread_count(db: AsyncSession, user_id: int) -> int:
    """Number of unread notifications owned by ``user_id`` (for the navbar badge)."""
    stmt = select(func.count()).select_from(Notification).where(
        Notification.user_id == user_id,
        Notification.is_read.is_(False),
    )
    return (await db.execute(stmt)).scalar_one()

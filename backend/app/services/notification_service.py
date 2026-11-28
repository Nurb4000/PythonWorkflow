"""Helpers for creating and querying in-app notifications (Feature-Plan §2.3).

A notification is a single-user, read/unread-tracked message about an event that
matters to that user (task assignment, SLA breach, workflow completion/failure,
...). Creation flushes rather than commits so the row is owned by the caller's
transaction -- e.g. a task-assignment notification commits alongside the task it
describes and rolls back with it.
"""
import json
import logging
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.schemas import Notification
from app.services.notification_channels import (
    DEFAULT_ROUTING,
    NotificationTarget,
    notification_dispatcher,
)

logger = logging.getLogger(__name__)

# system_settings key holding the JSON notification-type -> [channel types] routing.
ROUTING_SETTING_KEY = "notification_channel_routing"


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


# ---------------------------------------------------------------------------
# G4: external-channel configuration + routing
# ---------------------------------------------------------------------------


async def load_channel_overrides() -> None:
    """Apply DB-persisted channel overrides onto runtime settings (startup only).

    Mirrors ``email_service.load_smtp_overrides``: values live in
    ``system_settings`` so admins can configure channels from the UI and survive
    restarts. Missing keys fall back to whatever env/config already provided.
    """
    from app.core.database import async_session_factory
    from app.models.system_settings import SystemSetting

    keys = ("slack_webhook_url", "webhook_url", "webhook_secret")
    try:
        async with async_session_factory() as db:
            stmt = select(SystemSetting).where(SystemSetting.key.in_(keys))
            rows = {r.key: r.value for r in (await db.execute(stmt)).scalars().all()}
    except Exception as e:  # never block startup on config loading
        logger.error("Could not load notification channel overrides: %s", e)
        return

    def _db(key: str) -> str | None:
        return rows.get(key)

    if _db("slack_webhook_url") is not None:
        settings.slack_webhook_url = _db("slack_webhook_url")
    if _db("webhook_url") is not None:
        settings.webhook_url = _db("webhook_url")
    if _db("webhook_secret") is not None:
        settings.webhook_secret = _db("webhook_secret")


async def load_routing(db: AsyncSession) -> dict[str, list[str]]:
    """Routing map from ``system_settings`` (or :data:`DEFAULT_ROUTING` if unset)."""
    from app.api.system_settings import get_setting

    raw = await get_setting(db, ROUTING_SETTING_KEY, "")
    if not raw:
        return dict(DEFAULT_ROUTING)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and all(
            isinstance(k, str) and isinstance(v, list) for k, v in parsed.items()
        ):
            return parsed
    except (json.JSONDecodeError, TypeError):
        logger.warning("Invalid %s JSON; falling back to default routing", ROUTING_SETTING_KEY)
    return dict(DEFAULT_ROUTING)


async def apply_routing(db: AsyncSession) -> None:
    """Load routing from the DB and install it on the process-wide dispatcher."""
    routing = await load_routing(db)
    notification_dispatcher.routing.clear()
    notification_dispatcher.routing.update(routing)


async def notify(
    db: AsyncSession,
    user,
    type: str,
    title: str,
    message: str = "",
    *,
    related_entity_type: Optional[str] = None,
    related_entity_id: Optional[int] = None,
    context: Optional[dict] = None,
    dispatch: bool = True,
) -> tuple:
    """Create an in-app notification for ``user`` and dispatch external channels.

    Returns ``(notification, results)`` where ``results`` maps channel name ->
    list of :class:`DeliveryResult`. External delivery is best-effort; a failure
    here never raises.
    """
    notification = await create_notification(
        db,
        user_id=user.id,
        title=title,
        message=message,
        type=type,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
    )
    results: dict = {}
    if dispatch:
        # M4: carry the tenant on the external delivery so its execution-log row
        # can be attributed to the same tenant as the in-app notification.
        log_context = dict(context or {})
        log_context.setdefault("tenant_id", getattr(user, "tenant_id", None))
        target = NotificationTarget(
            type=type,
            title=title,
            message=message,
            recipients=[user.email] if getattr(user, "email", None) else [],
            context=log_context,
            entity_type=related_entity_type,
            entity_id=related_entity_id,
        )
        results = await notification_dispatcher.dispatch(target)
    return notification, results


async def notify_admins(
    type: str,
    title: str,
    message: str = "",
    *,
    context: Optional[dict] = None,
) -> dict:
    """Push an admin-facing event through every configured external channel.

    Uses ``settings.admin_notify_email`` as the recipient. Best-effort; never
    raises. Returns the channel -> results map (empty when nothing is configured).
    """
    recipients = [settings.admin_notify_email] if settings.admin_notify_email else []
    target = NotificationTarget(
        type=type, title=title, message=message, recipients=recipients, context=context or {}
    )
    return await notification_dispatcher.dispatch(target)

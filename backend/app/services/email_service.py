"""
SMTP email service (P1.2 admin notices + P2.1 workflow emails).

Effective configuration lives on app.core.config.settings (smtp_* fields).
Admins may override it at runtime via the Settings page; overrides are
persisted in the system_settings table and re-applied on startup by
load_smtp_overrides(), so they survive restarts.

Every send attempt returns stage-level diagnostics instead of swallowing
errors, so misconfiguration is diagnosable from the UI (Settings →
"Send Test Email") rather than only from container logs.
"""
import logging
import smtplib
from datetime import datetime
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)

SMTP_SETTING_KEYS = ("smtp_host", "smtp_port", "smtp_username", "smtp_password", "smtp_from", "smtp_tls")


def _build_msg(
    from_addr: str, to: str, subject: str, body: str, html_body: str | None = None
) -> EmailMessage:
    """Build an email message.

    I12 fix: supports multipart/alternative (text + HTML) when html_body is provided.
    Falls back to plain text when only body is given.
    """
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    if html_body:
        msg.add_alternative(html_body, subtype="html")

    return msg


async def load_smtp_overrides() -> None:
    """Apply DB-persisted SMTP settings onto the runtime settings object.

    Mirrors the email monitor's pattern of storing admin-configurable values
    in system_settings; called once at application startup. Missing keys fall
    back to whatever env/config already provided.
    """
    from sqlalchemy import select

    from app.core.database import async_session_factory
    from app.models.system_settings import SystemSetting

    try:
        async with async_session_factory() as db:
            stmt = select(SystemSetting).where(SystemSetting.key.in_(SMTP_SETTING_KEYS))
            rows = {r.key: r.value for r in (await db.execute(stmt)).scalars().all()}
    except Exception as e:  # never block startup on config loading
        logger.error("Could not load SMTP settings overrides: %s", e)
        return

    def _db(key: str) -> str | None:
        return rows.get(key)

    if _db("smtp_host") is not None:
        settings.smtp_host = _db("smtp_host")
    if _db("smtp_port"):
        try:
            settings.smtp_port = int(_db("smtp_port"))
        except ValueError:
            pass
    if _db("smtp_username") is not None:
        settings.smtp_username = _db("smtp_username")
    if _db("smtp_password") is not None and _db("smtp_password") != "":
        settings.smtp_password = _db("smtp_password")
    if _db("smtp_from") is not None:
        settings.smtp_from = _db("smtp_from")
    if _db("smtp_tls") is not None:
        settings.smtp_tls = (_db("smtp_tls") or "").lower() != "false"


def smtp_diagnostics() -> dict:
    """Non-secret summary of the effective SMTP configuration."""
    return {
        "host": settings.smtp_host or "",
        "port": settings.smtp_port,
        "tls": bool(settings.smtp_tls),
        "from_addr": settings.smtp_from or "",
        "username_configured": bool(settings.smtp_username),
        "configured": bool(settings.smtp_host),
    }


def _smtp_deliver(msg: EmailMessage) -> dict:
    """Attempt delivery with granular stages. Never raises.

    Returns {"ok": bool, "stage": str|None, "error": str|None} where stage is
    one of connect/starttls/login/send.
    """
    if not settings.smtp_host:
        return {"ok": False, "stage": "config", "error": "SMTP host not configured"}
    try:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
    except Exception as e:
        return {"ok": False, "stage": "connect", "error": f"{type(e).__name__}: {e}"}
    try:
        try:
            if settings.smtp_tls:
                server.starttls()
        except Exception as e:
            return {"ok": False, "stage": "starttls", "error": f"{type(e).__name__}: {e}"}
        try:
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
        except Exception as e:
            return {"ok": False, "stage": "login", "error": f"{type(e).__name__}: {e}"}
        try:
            server.send_message(msg)
        except Exception as e:
            return {"ok": False, "stage": "send", "error": f"{type(e).__name__}: {e}"}
    finally:
        try:
            server.quit()
        except Exception:
            pass
    logger.info("Email sent to %s: %s", msg["To"], msg["Subject"])
    return {"ok": True, "stage": None, "error": None}


def _send(msg: EmailMessage) -> bool:
    """Send via SMTP. Returns True on success (details logged)."""
    result = _smtp_deliver(msg)
    if not result["ok"]:
        logger.error(
            "Failed to send email at stage '%s': %s (subject=%s)",
            result["stage"], result["error"], msg["Subject"],
        )
    return result["ok"]


def notify_admin(subject: str, body: str) -> bool:
    """Best-effort admin notice email. Never raises; returns True if sent."""
    if not settings.admin_notify_email:
        logger.warning("Admin notify email not configured: %s", subject)
        return False
    msg = _build_msg(settings.smtp_from, settings.admin_notify_email, subject, body)
    return _send(msg)


def send_email(
    to: str,
    subject: str,
    body: str,
    from_addr: str | None = None,
    html_body: str | None = None,
) -> dict:
    """Send a workflow email. Returns result dict (never raises).

    I12 fix: accepts optional html_body for multipart/alternative messages.
    """
    addr_from = from_addr or settings.smtp_from
    msg = _build_msg(addr_from, to, subject, body, html_body=html_body)
    result = _smtp_deliver(msg)
    return {
        "to": to,
        "subject": subject,
        "sent": result["ok"],
        "stage": result["stage"],
        "error": result["error"],
        "executed_at": datetime.utcnow().isoformat(),
    }


def send_test_email(to: str, subject: str = "Instant Workflow — test email") -> dict:
    """Send a test email with full diagnostics for the Settings page."""
    msg = _build_msg(settings.smtp_from or "no-reply@localhost", to, subject,
                     f"This is a test email sent at {datetime.utcnow().isoformat()}Z.")
    result = _smtp_deliver(msg)
    return {
        "ok": result["ok"],
        "stage": result["stage"],
        "error": result["error"],
        "to": to,
        **smtp_diagnostics(),
    }

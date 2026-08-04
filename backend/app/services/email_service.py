"""
SMTP email service (P1.2 admin notices + P2.1 workflow emails).

SMTP is configured via settings (see Settings.smtp_*).
When no SMTP host is configured the service is a no-op that logs instead of
sending, so dev/test environments never need a mail server.
"""
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


def _build_msg(from_addr: str, to: str, subject: str, body: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


def _send(msg: EmailMessage) -> bool:
    """Actually send via SMTP. Returns True on success."""
    if not settings.smtp_host:
        logger.warning("SMTP not configured, email not sent: %s", msg["Subject"])
        return False
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            if settings.smtp_tls:
                server.starttls()
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(msg)
        logger.info("Email sent to %s: %s", msg["To"], msg["Subject"])
        return True
    except Exception as e:
        logger.error("Failed to send email: %s", e)
        return False


def notify_admin(subject: str, body: str) -> bool:
    """Best-effort admin notice email. Never raises; returns True if sent."""
    if not settings.admin_notify_email:
        logger.warning("Admin notify email not configured: %s", subject)
        return False
    msg = _build_msg(settings.smtp_from, settings.admin_notify_email, subject, body)
    return _send(msg)


def send_email(to: str, subject: str, body: str, from_addr: str | None = None) -> dict:
    """Send a workflow email. Returns result dict (never raises)."""
    addr_from = from_addr or settings.smtp_from
    msg = _build_msg(addr_from, to, subject, body)
    sent = _send(msg)
    return {
        "to": to,
        "subject": subject,
        "sent": sent,
        "executed_at": __import__("datetime").datetime.utcnow().isoformat(),
    }

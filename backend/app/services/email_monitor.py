"""
IMAP email monitor service - polls incoming mail for workflow trigger tags.

Monitors an IMAP mailbox at configurable intervals. Parses email body/subject
for {Rule####} tags to determine which workflow to trigger. Saves attachments
to disk and passes file paths into workflow input data. Moves processed emails
to the configured trash folder.
"""
import imaplib
import email
import logging
import os
import re
from email.header import decode_header
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.email_trigger import EmailProcessingLog
from app.models.schemas import Workflow, WorkflowRun
from app.services.scheduler import scheduler_service
from app.services.email_service import notify_admin

logger = logging.getLogger(__name__)

ATTACHMENTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "backend_data", "email_attachments"
)

RULE_PATTERN = re.compile(r"\{Rule(\d+)\}")


class EmailMonitorService:
    """Polls IMAP for incoming emails and triggers workflows based on {Rule####} tags."""

    def __init__(self):
        self.imap_conn = None
        self._settings_cache: Dict[str, str] = {}
        self._poll_job_id = "email_monitor_poll"

    # ------------------------------------------------------------------
    # Settings helpers
    # ------------------------------------------------------------------

    async def _load_settings(self) -> Dict[str, str]:
        """Load IMAP settings from system_settings table."""
        if not self._settings_cache:
            async with async_session_factory() as db:
                keys = [
                    "imap_monitor_enabled",
                    "imap_host",
                    "imap_port",
                    "imap_username",
                    "imap_password",
                    "imap_poll_interval",
                    "imap_folder",
                    "imap_trash_folder",
                    "imap_default_workflow_id",
                ]
                stmt = select(EmailProcessingLog.__table__.c.key)  # placeholder
                from app.models.system_settings import SystemSetting
                stmt = select(SystemSetting).where(SystemSetting.key.in_(keys))
                result = await db.execute(stmt)
                for row in result.scalars().all():
                    self._settings_cache[row.key] = row.value or ""
        return self._settings_cache

    def _get_setting(self, key: str, default: str = "") -> str:
        return self._settings_cache.get(key, default)

    def invalidate_settings_cache(self):
        self._settings_cache = {}

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Establish IMAP connection using current settings."""
        host = self._get_setting("imap_host")
        port = int(self._get_setting("imap_port", "993"))
        username = self._get_setting("imap_username")
        password = self._get_setting("imap_password")

        if not host or not username:
            logger.warning("IMAP monitor: host or username not configured")
            return False

        try:
            self.imap_conn = imaplib.IMAP4_SSL(host, port)
            self.imap_conn.login(username, password)
            logger.info(f"IMAP connected to {host}:{port}")
            return True
        except Exception as e:
            logger.error(f"IMAP connection failed: {e}")
            self.imap_conn = None
            return False

    def disconnect(self):
        """Close IMAP connection."""
        if self.imap_conn:
            try:
                self.imap_conn.logout()
            except Exception:
                pass
            self.imap_conn = None
            logger.info("IMAP disconnected")

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    async def poll(self):
        """Main polling loop - find unread emails, process each one."""
        enabled = self._get_setting("imap_monitor_enabled", "false").lower() == "true"
        if not enabled:
            return

        await self._load_settings()

        if not self.imap_conn or not self._is_connected():
            if not self.connect():
                return

        folder = self._get_setting("imap_folder", "INBOX")
        trash_folder = self._get_setting("imap_trash_folder", "Trash")

        try:
            self.imap_conn.select(folder, readonly=False)
            status, messages = self.imap_conn.search(None, "UNSEEN")
            if status != "OK":
                return

            uid_list = messages[0].split()
            if not uid_list:
                return

            logger.info(f"Found {len(uid_list)} unseen emails in {folder}")

            for uid_bytes in uid_list:
                uid = uid_bytes.decode("utf-8")
                await self._process_email(uid, folder, trash_folder)

        except Exception as e:
            logger.error(f"IMAP poll error: {e}")

    def _is_connected(self) -> bool:
        try:
            self.imap_conn.noop()
            return True
        except Exception:
            self.imap_conn = None
            return False

    # ------------------------------------------------------------------
    # Email processing
    # ------------------------------------------------------------------

    async def _process_email(self, uid: str, folder: str, trash_folder: str):
        """Fetch, parse, and trigger workflow for a single email."""
        try:
            status, msg_data = self.imap_conn.fetch(uid, "(RFC822)")
            if status != "OK":
                return

            raw_email = msg_data[0][1]
            email_msg = email.message_from_bytes(raw_email)

            email_data = self._parse_email(email_msg)
            rule_match = self._extract_rule_id(
                email_data.get("subject", "") + " " + email_data.get("body_text", "")
            )

            workflow_id = None
            triggered_by = "email"
            error_msg = ""

            if rule_match:
                workflow_id = int(rule_match)
                triggered_by = "email_rule"
            else:
                default_wf = self._get_setting("imap_default_workflow_id", "").strip()
                if default_wf:
                    try:
                        workflow_id = int(default_wf)
                        triggered_by = "email_default"
                    except ValueError:
                        error_msg = f"Invalid default workflow ID: {default_wf}"

            # Log the processing attempt
            log_entry = EmailProcessingLog(
                email_uid=uid,
                workflow_id=workflow_id,
                email_from=email_data.get("from", ""),
                email_subject=email_data.get("subject", ""),
                rule_tag=f"Rule{rule_match}" if rule_match else "",
                status="processing",
            )

            async with async_session_factory() as db:
                # Check for duplicate UID
                existing = await self._get_log_by_uid(db, uid)
                if existing:
                    logger.info(f"Email UID {uid} already processed, skipping")
                    return

                db.add(log_entry)
                await db.flush()
                log_id = log_entry.id

                # Verify workflow exists and is active
                if workflow_id:
                    stmt = select(Workflow).where(
                        Workflow.id == workflow_id, Workflow.is_active == True
                    )
                    result = await db.execute(stmt)
                    wf = result.scalar_one_or_none()

                    if not wf:
                        error_msg = (
                            f"Workflow {workflow_id} not found or inactive. "
                            f"Email from: {email_data.get('from', '')}, "
                            f"Subject: {email_data.get('subject', '')}"
                        )
                        await self._update_log(db, log_id, "failed", error_msg)
                        notify_admin(
                            f"Email trigger: workflow not found ({workflow_id})",
                            error_msg,
                        )
                        self._move_to_trash(uid, folder, trash_folder)
                        return

                # Save attachments
                attachment_paths = []
                if email_data.get("attachments"):
                    attachment_dir = os.path.join(ATTACHMENTS_DIR, uid)
                    os.makedirs(attachment_dir, exist_ok=True)
                    for att in email_data["attachments"]:
                        filepath = os.path.join(attachment_dir, att["filename"])
                        with open(filepath, "wb") as f:
                            f.write(att["data"])
                        attachment_paths.append({
                            "filename": att["filename"],
                            "filepath": filepath,
                            "content_type": att.get("content_type", "application/octet-stream"),
                            "size": len(att["data"]),
                        })

                # Build workflow input data
                input_data = {
                    "email_from": email_data.get("from", ""),
                    "email_to": email_data.get("to", ""),
                    "email_subject": email_data.get("subject", ""),
                    "email_body_text": email_data.get("body_text", ""),
                    "email_body_html": email_data.get("body_html", ""),
                    "email_date": email_data.get("date", ""),
                    "email_uid": uid,
                    "email_attachments": attachment_paths,
                    "rule_matched": rule_match,
                    "matched_workflow_id": workflow_id,
                }

                # Trigger workflow
                run = await scheduler_service.trigger_external_api(
                    workflow_id, input_data, None
                )

                await self._update_log(db, log_id, "completed", "", run.id)
                logger.info(
                    f"Email UID {uid} -> workflow {workflow_id}, run {run.id}"
                )

            # Move to trash after successful processing
            self._move_to_trash(uid, folder, trash_folder)

        except Exception as e:
            error_str = str(e)
            logger.error(f"Failed to process email UID {uid}: {error_str}")
            try:
                async with async_session_factory() as db:
                    existing = await self._get_log_by_uid(db, uid)
                    if existing:
                        await self._update_log(
                            db, existing.id, "failed", error_str
                        )
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Email parsing
    # ------------------------------------------------------------------

    def _parse_email(self, msg: email.message.Message) -> Dict[str, Any]:
        """Extract relevant fields from an email message."""
        result = {
            "from": self._decode_param(msg.get("From", "")),
            "to": self._decode_param(msg.get("To", "")),
            "subject": self._decode_header_safe(msg.get("Subject", "")),
            "date": msg.get("Date", ""),
            "body_text": "",
            "body_html": "",
            "attachments": [],
        }

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                disposition = str(part.get("Content-Disposition", ""))

                if content_type == "text/plain" and "attachment" not in disposition:
                    body = self._get_part_body(part)
                    if body and not result["body_text"]:
                        result["body_text"] = body

                elif content_type == "text/html" and "attachment" not in disposition:
                    body = self._get_part_body(part)
                    if body:
                        result["body_html"] = body

                elif "attachment" in disposition:
                    att_data = part.get_payload(decode=True)
                    if att_data:
                        filename = part.get_filename()
                        if filename:
                            filename = self._decode_header_safe(filename)
                        else:
                            filename = f"attachment_{len(result['attachments'])}"
                        result["attachments"].append({
                            "filename": filename,
                            "content_type": content_type,
                            "data": att_data,
                        })
        else:
            body = self._get_part_body(msg)
            if body:
                ct = msg.get_content_type()
                if ct == "text/html":
                    result["body_html"] = body
                else:
                    result["body_text"] = body

        return result

    def _get_part_body(self, part) -> str:
        """Decode and return the body of an email part."""
        payload = part.get_payload(decode=True)
        if not payload:
            return ""
        charset = part.get_content_charset() or "utf-8"
        try:
            return payload.decode(charset, errors="replace")
        except Exception:
            return payload.decode("utf-8", errors="replace")

    def _decode_header_safe(self, header_value: str) -> str:
        """Safely decode an email header value."""
        if not header_value:
            return ""
        decoded_parts = decode_header(header_value)
        result = []
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                result.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                result.append(part)
        return "".join(result)

    def _decode_param(self, param: str) -> str:
        """Decode a simple email parameter (From/To)."""
        return self._decode_header_safe(param)

    # ------------------------------------------------------------------
    # Rule extraction
    # ------------------------------------------------------------------

    def _extract_rule_id(self, text: str) -> Optional[str]:
        """Extract the first {Rule####} tag from text. Returns the number or None."""
        match = RULE_PATTERN.search(text)
        return match.group(1) if match else None

    # ------------------------------------------------------------------
    # IMAP operations
    # ------------------------------------------------------------------

    def _move_to_trash(self, uid: str, folder: str, trash_folder: str):
        """Move an email to the trash folder. Falls back to marking READ."""
        if not self.imap_conn:
            return

        try:
            # Try to copy to trash first
            self.imap_conn.select(trash_folder, readonly=False)
            status, _ = self.imap_conn.copy(uid, trash_folder)

            if status == "OK":
                # Copy succeeded, now delete from source
                self.imap_conn.select(folder, readonly=False)
                self.imap_conn.store(uid, "+FLAGS", "\\Deleted")
                self.imap_conn.expunge()
                logger.info(f"Email UID {uid} moved to {trash_folder}")
            else:
                self._fallback_mark_read(uid, folder)

        except Exception as e:
            logger.warning(f"Failed to move email {uid} to trash: {e}, marking READ instead")
            try:
                self._fallback_mark_read(uid, folder)
            except Exception:
                pass

    def _fallback_mark_read(self, uid: str, folder: str):
        """Mark email as READ (fallback when trash move fails)."""
        if not self.imap_conn:
            return
        self.imap_conn.select(folder, readonly=False)
        self.imap_conn.store(uid, "+FLAGS", "\\Seen")
        logger.info(f"Email UID {uid} marked as READ in {folder}")

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    async def _get_log_by_uid(self, db: AsyncSession, uid: str) -> Optional[EmailProcessingLog]:
        stmt = select(EmailProcessingLog).where(EmailProcessingLog.email_uid == uid)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _update_log(
        self, db: AsyncSession, log_id: int, status: str, error: str = "", run_id: Optional[int] = None
    ):
        stmt = select(EmailProcessingLog).where(EmailProcessingLog.id == log_id)
        result = await db.execute(stmt)
        entry = result.scalar_one_or_none()
        if entry:
            entry.status = status
            entry.error_message = error
            if run_id:
                entry.run_id = run_id
            await db.commit()

    # ------------------------------------------------------------------
    # Scheduler integration
    # ------------------------------------------------------------------

    def start_polling(self):
        """Add the email poll job to the APScheduler."""
        settings = self._settings_cache
        enabled = settings.get("imap_monitor_enabled", "false").lower() == "true"
        if not enabled:
            return

        interval = int(settings.get("imap_poll_interval", "300"))
        if interval < 30:
            interval = 30

        from app.services.scheduler import scheduler_service
        sched = scheduler_service.scheduler

        if sched.get_job(self._poll_job_id):
            sched.remove_job(self._poll_job_id)

        sched.add_job(
            self.poll,
            "interval",
            seconds=interval,
            id=self._poll_job_id,
            replace_existing=True,
        )
        logger.info(f"Email monitor polling started (every {interval}s)")

    def stop_polling(self):
        """Remove the email poll job from the scheduler."""
        try:
            from app.services.scheduler import scheduler_service
            sched = scheduler_service.scheduler
            if sched.get_job(self._poll_job_id):
                sched.remove_job(self._poll_job_id)
                logger.info("Email monitor polling stopped")
        except Exception as e:
            logger.warning(f"Error stopping email poll: {e}")

    def restart_polling(self):
        """Restart polling with updated settings."""
        self.stop_polling()
        self.invalidate_settings_cache()
        self.start_polling()


# Global instance
email_monitor = EmailMonitorService()

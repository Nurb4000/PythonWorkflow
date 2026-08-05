"""
Settings API endpoints for system configuration
"""
import os

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File as FileParam, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.core.database import get_db
from app.models.auth import User
from app.models.system_settings import SystemSetting
from app.api.auth import get_current_user

router = APIRouter()

BRANDING_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "uploads", "branding"
)


async def get_setting(db: AsyncSession, key: str, default: str = "") -> str:
    """Get a setting value from the DB"""
    stmt = select(SystemSetting).where(SystemSetting.key == key)
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    return row.value if row else default


async def set_setting(db: AsyncSession, key: str, value: str) -> None:
    """Set a setting value in the DB"""
    stmt = select(SystemSetting).where(SystemSetting.key == key)
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row:
        row.value = value
    else:
        db.add(SystemSetting(key=key, value=value))
    await db.commit()


DEFAULT_SYSTEM_NAME = "Workflow System"


class Settings:
    """System settings stored in memory (could be DB later)"""
    llama_cpp_url: str = "http://localhost:8081"
    llama_cpp_model: str = "default"
    email_smtp_host: str = ""
    email_smtp_port: int = 587
    email_username: str = ""
    email_password: str = ""
    email_from: str = ""


settings = Settings()


@router.get("/branding")
async def get_branding(
    db: AsyncSession = Depends(get_db)
):
    """Get public branding settings (no auth required)"""
    system_name = await get_setting(db, "branding_system_name", DEFAULT_SYSTEM_NAME)
    logo_filename = await get_setting(db, "branding_logo", "")

    return {
        "system_name": system_name,
        "logo_url": "/api/branding/logo" if logo_filename else None
    }


@router.get("/branding/logo")
async def get_branding_logo(
    db: AsyncSession = Depends(get_db)
):
    """Serve the uploaded branding logo (public)"""
    logo_filename = await get_setting(db, "branding_logo", "")
    if not logo_filename:
        raise HTTPException(status_code=404, detail="No logo uploaded")

    path = os.path.join(BRANDING_DIR, logo_filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Logo not found")

    return FileResponse(path)


@router.put("/settings/branding")
async def update_branding(
    system_name: Optional[str] = None,
    request: Request = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update branding settings (admin only)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    # Try to read JSON body if query params not provided
    if request and request.headers.get("content-type") == "application/json":
        body = await request.json()
        system_name = system_name or body.get("system_name")

    if system_name is not None and system_name.strip():
        await set_setting(db, "branding_system_name", system_name.strip())

    return {"message": "Branding updated"}


@router.post("/settings/branding/logo")
async def upload_branding_logo(
    file: UploadFile = FileParam(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload a branding logo (admin only)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        os.makedirs(BRANDING_DIR, exist_ok=True)

        original = file.filename or "logo.png"
        ext = os.path.splitext(original)[1].lower() or ".png"
        if ext not in [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico"]:
            raise HTTPException(status_code=400, detail="Unsupported image format")

        filename = f"logo{ext}"
        content = await file.read()
        with open(os.path.join(BRANDING_DIR, filename), "wb") as f:
            f.write(content)

        await set_setting(db, "branding_logo", filename)

        return {"message": "Logo uploaded", "logo_url": "/api/branding/logo"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/settings")
async def get_settings(
    current_user: User = Depends(get_current_user)
):
    """Get system settings (admin only)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    return {
        "llama_cpp_url": settings.llama_cpp_url,
        "llama_cpp_model": settings.llama_cpp_model,
        "email_smtp_host": settings.email_smtp_host,
        "email_smtp_port": settings.email_smtp_port,
        "email_from": settings.email_from
    }


@router.put("/settings/llm")
async def update_llm_settings(
    llama_cpp_url: str,
    llama_cpp_model: str = "default",
    current_user: User = Depends(get_current_user)
):
    """Update LLM settings (admin only)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    settings.llama_cpp_url = llama_cpp_url
    settings.llama_cpp_model = llama_cpp_model
    
    return {"message": "LLM settings updated", "settings": {
        "llama_cpp_url": settings.llama_cpp_url,
        "llama_cpp_model": settings.llama_cpp_model
    }}


@router.put("/settings/email")
async def update_email_settings(
    smtp_host: str,
    smtp_port: int = 587,
    username: str = "",
    password: str = "",
    from_address: str = "",
    current_user: User = Depends(get_current_user)
):
    """Update email settings (admin only)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    settings.email_smtp_host = smtp_host
    settings.email_smtp_port = smtp_port
    settings.email_username = username
    settings.email_password = password
    settings.email_from = from_address
    
    return {"message": "Email settings updated"}


@router.post("/settings/test-email")
async def test_email(
    to_email: str,
    subject: str = "Test Email",
    body: str = "This is a test email from the workflow system.",
    current_user: User = Depends(get_current_user)
):
    """Send test email (admin only)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    if not settings.email_smtp_host:
        raise HTTPException(status_code=400, detail="Email SMTP host not configured")

    # TODO: Implement actual email sending
    return {
        "message": f"Test email would be sent to {to_email}",
        "smtp_host": settings.email_smtp_host,
        "from": settings.email_from
    }


# ------------------------------------------------------------------
# IMAP Incoming Email Monitor Settings
# ------------------------------------------------------------------

IMAP_SETTING_KEYS = [
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


@router.get("/settings/imap")
async def get_imap_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get IMAP monitor settings (admin only)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    imap_enabled = await get_setting(db, "imap_monitor_enabled", "false")
    return {
        "imap_monitor_enabled": imap_enabled.lower() == "true",
        "imap_host": await get_setting(db, "imap_host", ""),
        "imap_port": int(await get_setting(db, "imap_port", "993")),
        "imap_username": await get_setting(db, "imap_username", ""),
        "imap_poll_interval": int(await get_setting(db, "imap_poll_interval", "300")),
        "imap_folder": await get_setting(db, "imap_folder", "INBOX"),
        "imap_trash_folder": await get_setting(db, "imap_trash_folder", "Trash"),
        "imap_default_workflow_id": await get_setting(db, "imap_default_workflow_id", ""),
    }


@router.put("/settings/imap")
async def update_imap_settings(
    imap_monitor_enabled: bool = False,
    imap_host: str = "",
    imap_port: int = 993,
    imap_username: str = "",
    imap_password: str = "",
    imap_poll_interval: int = 300,
    imap_folder: str = "INBOX",
    imap_trash_folder: str = "Trash",
    imap_default_workflow_id: str = "",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update IMAP monitor settings (admin only)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    await set_setting(db, "imap_monitor_enabled", "true" if imap_monitor_enabled else "false")
    await set_setting(db, "imap_host", imap_host)
    await set_setting(db, "imap_port", str(imap_port))
    await set_setting(db, "imap_username", imap_username)
    await set_setting(db, "imap_password", imap_password)
    await set_setting(db, "imap_poll_interval", str(imap_poll_interval))
    await set_setting(db, "imap_folder", imap_folder)
    await set_setting(db, "imap_trash_folder", imap_trash_folder)
    await set_setting(db, "imap_default_workflow_id", str(imap_default_workflow_id))

    from app.services.scheduler import scheduler_service
    await scheduler_service.start_email_monitor()

    return {"message": "IMAP settings updated"}


@router.post("/settings/imap/test")
async def test_imap_connection(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Test IMAP connection and show what emails would be processed (admin only)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    from app.services.email_monitor import email_monitor

    await email_monitor._load_settings()

    host = email_monitor._get_setting("imap_host")
    if not host:
        raise HTTPException(status_code=400, detail="IMAP host not configured")

    connected = email_monitor.connect()
    if not connected:
        email_monitor.disconnect()
        raise HTTPException(status_code=500, detail="Failed to connect to IMAP server")

    folder = email_monitor._get_setting("imap_folder", "INBOX")
    try:
        email_monitor.imap_conn.select(folder, readonly=True)
        status, messages = email_monitor.imap_conn.search(None, "UNSEEN")
        uid_list = messages[0].split() if status == "OK" else []

        preview = []
        for uid_bytes in uid_list[:10]:
            uid = uid_bytes.decode("utf-8")
            st, data = email_monitor.imap_conn.fetch(uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])")
            if st == "OK" and data[0][1]:
                header_msg = email.message_from_bytes(data[0][1])
                rule_match = email_monitor._extract_rule_id(
                    header_msg.get("Subject", "")
                )
                preview.append({
                    "uid": uid,
                    "from": header_msg.get("From", ""),
                    "subject": header_msg.get("Subject", ""),
                    "rule_tag": f"Rule{rule_match}" if rule_match else "(default workflow)",
                })

        result = {
            "connected": True,
            "folder": folder,
            "unseen_count": len(uid_list),
            "preview": preview,
        }
    except Exception as e:
        result = {
            "connected": True,
            "error": f"Failed to list emails: {e}",
        }
    finally:
        email_monitor.disconnect()

    return result


@router.post("/settings/imap/poll-now")
async def poll_imap_now(
    current_user: User = Depends(get_current_user)
):
    """Force an immediate IMAP poll (admin only)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    from app.services.email_monitor import email_monitor

    await email_monitor._load_settings()
    enabled = email_monitor._get_setting("imap_monitor_enabled", "false").lower() == "true"
    if not enabled:
        raise HTTPException(status_code=400, detail="IMAP monitor is not enabled")

    await email_monitor.poll()

    return {"message": "IMAP poll completed"}


# ------------------------------------------------------------------
# Portal Banner Settings
# ------------------------------------------------------------------

BANNER_SETTING_KEYS = [
    "banner_enabled",
    "banner_title",
    "banner_message",
    "banner_color",
]

DEFAULT_BANNER_COLOR = "#f39c12"


@router.get("/settings/banner")
async def get_banner_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get portal banner settings (admin only)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    enabled = await get_setting(db, "banner_enabled", "false")
    return {
        "banner_enabled": enabled.lower() == "true",
        "banner_title": await get_setting(db, "banner_title", ""),
        "banner_message": await get_setting(db, "banner_message", ""),
        "banner_color": await get_setting(db, "banner_color", DEFAULT_BANNER_COLOR),
    }


@router.put("/settings/banner")
async def update_banner_settings(
    banner_enabled: bool = False,
    banner_title: str = "",
    banner_message: str = "",
    banner_color: str = DEFAULT_BANNER_COLOR,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update portal banner settings (admin only)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    await set_setting(db, "banner_enabled", "true" if banner_enabled else "false")
    await set_setting(db, "banner_title", banner_title)
    await set_setting(db, "banner_message", banner_message)
    await set_setting(db, "banner_color", banner_color)

    return {"message": "Banner settings updated"}


@router.get("/portal/banner")
async def get_portal_banner(
    db: AsyncSession = Depends(get_db)
):
    """Get active portal banner (public, no auth required)"""
    enabled = await get_setting(db, "banner_enabled", "false")
    if enabled.lower() != "true":
        return {"enabled": False}

    return {
        "enabled": True,
        "title": await get_setting(db, "banner_title", ""),
        "message": await get_setting(db, "banner_message", ""),
        "color": await get_setting(db, "banner_color", DEFAULT_BANNER_COLOR),
    }

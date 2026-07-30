"""
Settings API endpoints for system configuration
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.core.database import get_db
from app.models.auth import User
from app.api.auth import get_current_user

router = APIRouter()


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

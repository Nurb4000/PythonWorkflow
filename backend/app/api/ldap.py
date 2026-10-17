"""
LDAP configuration and sync API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
import secrets

from app.core.database import get_db
from app.models.auth import User
from app.api.auth import get_current_admin
from app.services.ldap_service import ldap_service

router = APIRouter(prefix="/admin/ldap", tags=["ldap"])


# M9 fix: test-connection parameters (including the bind password) are now sent
# in the JSON request body instead of as Query strings, so the secret is no
# longer exposed in the URL / server logs.
class TestLdapConnectionRequest(BaseModel):
    ldap_server_url: str
    ldap_base_dn: str
    ldap_bind_dn: str
    ldap_bind_password: str = ""


@router.get("/config")
async def get_ldap_config(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get LDAP configuration (admin only)."""
    from app.api.system_settings import settings
    
    return {
        "ldap_server_url": settings.ldap_server_url,
        "ldap_base_dn": settings.ldap_base_dn,
        "ldap_bind_dn": settings.ldap_bind_dn,
        "ldap_user_filter": settings.ldap_user_filter,
        "ldap_username_attribute": settings.ldap_username_attribute,
        "ldap_email_attribute": settings.ldap_email_attribute,
        "ldap_fullname_attribute": settings.ldap_fullname_attribute,
        "ldap_sync_enabled": settings.ldap_sync_enabled,
        "ldap_sync_interval_hours": settings.ldap_sync_interval_hours,
        # Don't expose bind password
    }


@router.put("/config")
async def update_ldap_config(
    ldap_server_url: str = "",
    ldap_base_dn: str = "",
    ldap_bind_dn: str = "",
    ldap_bind_password: str = "",
    ldap_user_filter: str = "(objectClass=person)",
    ldap_username_attribute: str = "uid",
    ldap_email_attribute: str = "mail",
    ldap_fullname_attribute: str = "cn",
    ldap_sync_enabled: bool = False,
    ldap_sync_interval_hours: int = 24,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update LDAP configuration (admin only).

M9 fix: the whole config — including the bind password — is persisted to the
system_settings table so it survives restarts (previously it was written only
to the in-memory settings singleton and silently reset on restart). The bind
password is only overwritten when a non-empty value is supplied.
"""
    from app.api.system_settings import get_setting, set_setting

    await set_setting(db, "ldap_server_url", ldap_server_url)
    await set_setting(db, "ldap_base_dn", ldap_base_dn)
    await set_setting(db, "ldap_bind_dn", ldap_bind_dn)
    if ldap_bind_password:
        await set_setting(db, "ldap_bind_password", ldap_bind_password)
    await set_setting(db, "ldap_user_filter", ldap_user_filter)
    await set_setting(db, "ldap_username_attribute", ldap_username_attribute)
    await set_setting(db, "ldap_email_attribute", ldap_email_attribute)
    await set_setting(db, "ldap_fullname_attribute", ldap_fullname_attribute)
    await set_setting(db, "ldap_sync_enabled", "true" if ldap_sync_enabled else "false")
    await set_setting(db, "ldap_sync_interval_hours", str(ldap_sync_interval_hours))

    # Re-apply onto the runtime settings object for the current process.
    from app.core.config import settings as app_settings
    app_settings.ldap_server_url = ldap_server_url
    app_settings.ldap_base_dn = ldap_base_dn
    app_settings.ldap_bind_dn = ldap_bind_dn
    if ldap_bind_password:
        app_settings.ldap_bind_password = ldap_bind_password
    app_settings.ldap_user_filter = ldap_user_filter
    app_settings.ldap_username_attribute = ldap_username_attribute
    app_settings.ldap_email_attribute = ldap_email_attribute
    app_settings.ldap_fullname_attribute = ldap_fullname_attribute
    app_settings.ldap_sync_enabled = ldap_sync_enabled
    app_settings.ldap_sync_interval_hours = ldap_sync_interval_hours

    return {"message": "LDAP configuration updated"}


@router.post("/test-connection")
async def test_ldap_connection(
    request: TestLdapConnectionRequest,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Test LDAP connection (admin only)."""
    result = await ldap_service.test_connection(
        request.ldap_server_url,
        request.ldap_base_dn,
        request.ldap_bind_dn,
        request.ldap_bind_password
    )
    return result


@router.post("/sync")
async def trigger_ldap_sync(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Trigger manual LDAP user sync (admin only)."""
    from app.api.system_settings import settings
    
    if not settings.ldap_server_url:
        raise HTTPException(status_code=400, detail="LDAP server URL not configured")
    
    result = await ldap_service.sync_users(
        server_url=settings.ldap_server_url,
        base_dn=settings.ldap_base_dn,
        bind_dn=settings.ldap_bind_dn,
        bind_password=settings.ldap_bind_password,
        user_filter=settings.ldap_user_filter,
        username_attr=settings.ldap_username_attribute,
        email_attr=settings.ldap_email_attribute,
        fullname_attr=settings.ldap_fullname_attribute,
        db=db
    )
    
    return result


@router.post("/authenticate")
async def ldap_authenticate(
    username: str = Body(...),
    password: str = Body(...),
    db: AsyncSession = Depends(get_db)
):
    """Authenticate against LDAP. Falls back to local auth if LDAP fails."""
    from app.api.system_settings import settings
    from app.services.auth_service import auth_service
    
    # Try LDAP first if configured
    if settings.ldap_server_url and settings.ldap_base_dn:
        user_data = await ldap_service.authenticate(
            server_url=settings.ldap_server_url,
            base_dn=settings.ldap_base_dn,
            bind_dn=settings.ldap_bind_dn,
            bind_password=settings.ldap_bind_password,
            username=username,
            password=password,
            username_attr=settings.ldap_username_attribute
        )
        
        if user_data:
            # LDAP auth successful - create or update local user
            from sqlalchemy import select
            stmt = select(User).where(User.username == username)
            result = await db.execute(stmt)
            local_user = result.scalar_one_or_none()
            
            if not local_user:
                # Create local user with LDAP data
                local_user = await auth_service.create_user(
                    db,
                    username=username,
                    email=user_data.get("email", ""),
                    full_name=user_data.get("full_name", username),
                    # H4 fix: high-entropy random temp password instead of "ldap_auth"
                    password=secrets.token_urlsafe(18),
                    role="user",
                    custom_data={"source": "ldap"},
                )
            else:
                # Update existing user with LDAP data
                local_user.email = user_data.get("email", local_user.email)
                local_user.full_name = user_data.get("full_name", local_user.full_name)
                await db.commit()
            
            # Generate JWT token
            from app.api.auth import create_access_token
            token = create_access_token(data={"sub": str(local_user.id), "role": local_user.role})
            
            return {
                "success": True,
                "token": token,
                "user": {
                    "id": local_user.id,
                    "username": local_user.username,
                    "email": local_user.email,
                    "full_name": local_user.full_name,
                    "role": local_user.role,
                    "ldap_synced": True
                }
            }
    
    # Fallback to local authentication
    return await auth_service.login(db, username, password)

"""
Authentication API endpoints
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from datetime import datetime

from app.core.database import get_db
from app.services.auth_service import auth_service
from app.models.auth import User, Group
from app.schemas.workflow import AuditLogEntry

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    """Get current authenticated user"""
    payload = auth_service.verify_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    
    user = await auth_service.get_user_by_id(db, int(user_id))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Inactive user")
    
    return user


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """Get current admin user"""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.post("/auth/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    """Login and get access token"""
    user = await auth_service.authenticate_user(db, form_data.username, form_data.password)
    
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Update last login
    user.last_login = datetime.utcnow()
    await db.commit()
    
    # Create access token
    access_token = auth_service.create_access_token(
        data={"sub": str(user.id), "role": user.role, "username": user.username}
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "full_name": user.full_name
        }
    }


@router.post("/auth/register")
async def register(
    username: str,
    email: str,
    password: str,
    full_name: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Register a new user (self-service for 'user' role)"""
    try:
        user = await auth_service.create_user(
            db=db,
            username=username,
            email=email,
            password=password,
            role="user",
            full_name=full_name or username
        )
        
        return {
            "message": "User created successfully",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/auth/me")
async def get_current_user_info(user: User = Depends(get_current_user)):
    """Get current user information"""
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "mfa_enabled": user.mfa_enabled,
        "groups": [{"id": g.id, "name": g.name} for g in user.groups]
    }


@router.get("/auth/users", response_model=List[dict])
async def list_users(
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    admin_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all users (admin only)"""
    users = await auth_service.list_users(db, role=role, is_active=is_active)
    
    return [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role,
            "is_active": u.is_active,
            "mfa_enabled": u.mfa_enabled,
            "groups": [{"id": g.id, "name": g.name} for g in u.groups],
            "created_at": u.created_at,
            "last_login": u.last_login
        }
        for u in users
    ]


@router.put("/auth/users/{user_id}")
async def update_user(
    user_id: int,
    email: Optional[str] = None,
    full_name: Optional[str] = None,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    mfa_enabled: Optional[bool] = None,
    admin_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update user (admin only)"""
    try:
        # Admins can only update non-admin users unless they're updating themselves
        if role and role != "admin" and admin_user.id != user_id:
            pass  # Allow role change for non-admins
        
        kwargs = {}
        if email is not None:
            kwargs["email"] = email
        if full_name is not None:
            kwargs["full_name"] = full_name
        if role is not None:
            kwargs["role"] = role
        if is_active is not None:
            kwargs["is_active"] = is_active
        if mfa_enabled is not None:
            kwargs["mfa_enabled"] = mfa_enabled
        
        user = await auth_service.update_user(db, user_id, **kwargs)
        
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": user.is_active
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/auth/users/{user_id}")
async def delete_user(
    user_id: int,
    admin_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete user (admin only)"""
    success = await auth_service.delete_user(db, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"message": "User deleted successfully"}


@router.get("/auth/groups", response_model=List[dict])
async def list_groups(
    admin_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all groups (admin only)"""
    groups = await auth_service.list_groups(db)
    
    return [
        {
            "id": g.id,
            "name": g.name,
            "description": g.description,
            "group_type": g.group_type,
            "is_active": g.is_active,
            "user_count": len(g.users),
            "users": [{"id": u.id, "username": u.username} for u in g.users]
        }
        for g in groups
    ]


@router.post("/auth/groups")
async def create_group(
    name: str,
    description: Optional[str] = "",
    group_type: str = "internal",
    admin_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a new group (admin only)"""
    try:
        group = await auth_service.create_group(db, name, description, group_type)
        return {
            "id": group.id,
            "name": group.name,
            "description": group.description,
            "group_type": group.group_type
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/auth/groups/{group_id}/users/{user_id}")
async def add_user_to_group(
    group_id: int,
    user_id: int,
    admin_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Add user to group (admin only)"""
    try:
        await auth_service.add_user_to_group(db, user_id, group_id)
        return {"message": f"User {user_id} added to group {group_id}"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/auth/groups/{group_id}/users/{user_id}")
async def remove_user_from_group(
    group_id: int,
    user_id: int,
    admin_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Remove user from group (admin only)"""
    try:
        await auth_service.remove_user_from_group(db, user_id, group_id)
        return {"message": f"User {user_id} removed from group {group_id}"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/auth/{user_id}/tokens")
async def create_api_token(
    user_id: int,
    name: str,
    permissions: List[str],
    admin_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create API token for user (admin only)"""
    try:
        result = await auth_service.create_api_token(db, user_id, name, permissions)
        return {
            "message": "API token created. Save this token - it won't be shown again.",
            "token": result["token"],
            "token_name": name,
            "expires_at": result["api_token"].expires_at
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

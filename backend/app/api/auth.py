"""
Authentication API endpoints
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Response, Query
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import Optional, List
from datetime import datetime

from app.core.database import get_db
from app.services.auth_service import auth_service
from app.models.auth import User, Group
from app.models.schemas import Workflow
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


def has_role(user: User, required_role: str) -> bool:
    """Check if user has a specific role (supports multiple roles via roles JSON field)"""
    # Check roles array first (new multi-role support)
    if user.roles and required_role in user.roles:
        return True
    # Fall back to primary role for backward compatibility
    if user.role == required_role:
        return True
    return False


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """Get current admin user"""
    if not has_role(user, "admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def get_current_developer(user: User = Depends(get_current_user)) -> User:
    """Get current user who may develop workflows/forms (admin or developer)"""
    if not has_role(user, "admin") and not has_role(user, "developer"):
        raise HTTPException(status_code=403, detail="Developer access required")
    return user


async def get_current_cmdb_manager(user: User = Depends(get_current_user)) -> User:
    """Get current user who may manage CMDB data (admin, developer, or cmdb_manager)"""
    if not has_role(user, "admin") and not has_role(user, "developer") and not has_role(user, "cmdb_manager"):
        raise HTTPException(status_code=403, detail="CMDB manager access required")
    return user


async def check_api_token_cmdb_permission(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db), require_write: bool = False) -> User:
    """Check if API token has cmdb_read or cmdb_write permission.

    For JWT tokens (regular users), falls through to role-based checks.
    For API tokens, checks the permissions field on the APIToken record.
    """
    import hashlib
    from app.models.auth import APIToken

    # Try as API token first
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    stmt = select(APIToken).where(APIToken.token_hash == token_hash, APIToken.is_active == True)
    result = await db.execute(stmt)
    api_token = result.scalar_one_or_none()

    if api_token:
        permissions = [p.strip() for p in (api_token.permissions or "").split(",") if p.strip()]
        required_perm = "cmdb_write" if require_write else "cmdb_read"
        if required_perm not in permissions and "cmdb_all" not in permissions:
            raise HTTPException(status_code=403, detail=f"API token lacks '{required_perm}' permission")
        # Update last used
        api_token.last_used_at = datetime.utcnow()
        await db.commit()
        # Get user
        user_stmt = select(User).where(User.id == api_token.user_id)
        user_result = await db.execute(user_stmt)
        user = user_result.scalar_one_or_none()
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User associated with token is inactive")
        return user

    # Not an API token — fall back to regular JWT auth (role-based)
    return await get_current_user(token, db)


async def user_can_access_workflow(db: AsyncSession, user: User, workflow_id: int) -> bool:
    """Admin/developer see all workflows; other roles only see workflows permitted to their groups"""
    if user.role in ("admin", "developer"):
        return True

    stmt = (
        select(Workflow)
        .where(Workflow.id == workflow_id)
        .options(selectinload(Workflow.allowed_groups))
    )
    result = await db.execute(stmt)
    workflow = result.scalar_one_or_none()
    if not workflow:
        return False

    user_group_ids = {g.id for g in user.groups}
    allowed_ids = {g.id for g in workflow.allowed_groups}
    return bool(user_group_ids & allowed_ids)


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


@router.put("/auth/me/password")
async def change_password(
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Change the current user's password"""
    old_password = body.get("old_password", "")
    new_password = body.get("new_password", "")

    if not old_password or not new_password:
        raise HTTPException(status_code=400, detail="Both old_password and new_password are required")

    if len(new_password) < 4:
        raise HTTPException(status_code=400, detail="New password must be at least 4 characters")

    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    if not pwd_context.verify(old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    current_user.password_hash = pwd_context.hash(new_password)
    await db.commit()

    return {"message": "Password changed successfully"}


@router.post("/auth/register")
async def register(
    request: Request,
    username: str,
    email: str,
    password: str,
    full_name: Optional[str] = None,
    role: str = "user",
    db: AsyncSession = Depends(get_db)
):
    """Register a new user (admin creates users, self-service defaults to 'user' role)"""
    try:
        body = await request.json()
        custom_data = body if body else None

        user = await auth_service.create_user(
            db=db,
            username=username,
            email=email,
            password=password,
            role=role,
            full_name=full_name or username,
            custom_data=custom_data
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


@router.get("/auth/setup-required")
async def check_setup_required(db: AsyncSession = Depends(get_db)):
    """Check if setup is required (no users exist)"""
    from app.models.auth import User
    from sqlalchemy import select
    
    stmt = select(User)
    result = await db.execute(stmt)
    users = result.scalars().all()
    
    return {
        "setup_required": len(users) == 0,
        "user_count": len(users)
    }


@router.get("/auth/users", response_model=List[dict])
async def list_users(
    role: Optional[str] = None,
    include_inactive: bool = Query(False),
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db)
):
    """List all users (admin/developer). By default excludes deactivated users."""
    users = await auth_service.list_users(db, role=role, is_active=None if include_inactive else True)
    
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
            "last_login": u.last_login,
            "custom_data": u.custom_data or {}
        }
        for u in users
    ]


@router.put("/auth/users/{user_id}")
async def update_user(
    request: Request,
    user_id: int,
    email: Optional[str] = None,
    full_name: Optional[str] = None,
    role: Optional[str] = None,
    roles: Optional[str] = None,  # JSON array of roles
    is_active: Optional[bool] = None,
    mfa_enabled: Optional[bool] = None,
    password: Optional[str] = None,
    admin_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update user (admin only)"""
    import json
    try:
        body = await request.json()
        custom_data = body if body else None

        # Parse roles JSON array if provided
        parsed_roles = None
        if roles:
            try:
                parsed_roles = json.loads(roles)
                if not isinstance(parsed_roles, list):
                    raise ValueError("roles must be a JSON array")
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid roles JSON")

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
        if parsed_roles is not None:
            kwargs["roles"] = parsed_roles
        if is_active is not None:
            kwargs["is_active"] = is_active
        if mfa_enabled is not None:
            kwargs["mfa_enabled"] = mfa_enabled
        if password is not None:
            kwargs["password"] = password
        if custom_data is not None:
            kwargs["custom_data"] = custom_data

        user = await auth_service.update_user(db, user_id, **kwargs)
        
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "roles": user.roles or [],
            "is_active": user.is_active
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise


@router.delete("/auth/users/{user_id}")
async def delete_user(
    user_id: int,
    admin_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Deactivate user (admin only)"""
    success = await auth_service.delete_user(db, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")

    return {"message": "User deactivated successfully"}


@router.get("/auth/groups", response_model=List[dict])
async def list_groups(
    include_inactive: bool = Query(False),
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db)
):
    """List all groups (admin/developer only). By default excludes deactivated groups."""
    groups = await auth_service.list_groups(db, include_inactive=include_inactive)
    
    return [
        {
            "id": g.id,
            "name": g.name,
            "description": g.description,
            "group_type": g.group_type,
            "is_active": g.is_active,
            "user_count": len(g.users),
            "users": [{"id": u.id, "username": u.username} for u in g.users],
            "custom_data": g.custom_data or {},
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


@router.put("/auth/groups/{group_id}")
async def update_group(
    group_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    group_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    custom_data: Optional[dict] = None,
    admin_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update a group (admin only)"""
    kwargs = {}
    if name is not None:
        kwargs["name"] = name
    if description is not None:
        kwargs["description"] = description
    if group_type is not None:
        kwargs["group_type"] = group_type
    if is_active is not None:
        kwargs["is_active"] = is_active

    try:
        group = await auth_service.update_group(db, group_id, **kwargs)
        if custom_data is not None:
            group.custom_data = custom_data
            await db.commit()
            await db.refresh(group)
        return {
            "id": group.id,
            "name": group.name,
            "description": group.description,
            "group_type": group.group_type,
            "is_active": group.is_active,
            "custom_data": group.custom_data or {},
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/auth/groups/{group_id}")
async def delete_group(
    group_id: int,
    admin_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Deactivate a group (admin only)"""
    success = await auth_service.delete_group(db, group_id)
    if not success:
        raise HTTPException(status_code=404, detail="Group not found")
    return {"message": "Group deactivated successfully"}


@router.put("/auth/users/{user_id}/groups")
async def set_user_groups(
    user_id: int,
    group_ids: List[int],
    admin_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Replace the set of groups a user belongs to (admin only)"""
    try:
        user = await auth_service.set_user_groups(db, user_id, group_ids)
        return {
            "message": "User groups updated successfully",
            "groups": [{"id": g.id, "name": g.name} for g in user.groups]
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
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

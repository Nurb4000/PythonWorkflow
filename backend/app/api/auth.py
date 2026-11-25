"""
Authentication API endpoints
"""
import logging
import json
import time
from urllib.parse import urlparse
from collections import defaultdict

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException, Depends, Request, Response, Query, Body
from pydantic import BaseModel
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from typing import Optional, List
from datetime import datetime

from app.core.database import get_db
from app.services.auth_service import (
    auth_service,
    pwd_context,
    _utcnow,
    _as_aware,
    refresh_token_index,
)
from app.models.auth import User, Group, APIToken
from app.models.schemas import Workflow
from app.schemas.workflow import AuditLogEntry
from app.services.tenant_scoping import (
    get_active_tenant_id,
    get_requested_tenant_id,
    member_tenant_ids,
    list_member_tenants,
    set_active_tenant_id,
)

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

# Brute-force protection for /auth/login (findings #6). authenticate_user returns a
# uniform None on bad credentials, which stops user enumeration but does not bound
# the number of guesses. These helpers track failed logins per key and temporarily
# lock a key out, so credential stuffing / password guessing is bounded.
LOGIN_MAX_FAILURES = 5        # failures within...
LOGIN_WINDOW_SECONDS = 300    # ...this sliding window trigger a lockout...
LOGIN_LOCKOUT_SECONDS = 300   # ...which lasts this long before retries are allowed
# Per-IP sliding-window rate limit (defense in depth against distributed guessing /
# login DoS). Separate from the per-username lockout so one busy IP does not pin
# every account it touches.
LOGIN_IP_MAX = 120            # login attempts within...
LOGIN_IP_WINDOW_SECONDS = 60  # ...this window before a 429

_failed_login_attempts: dict[str, list[float]] = defaultdict(list)
_login_lockuntil: dict[str, float] = {}
_ip_login_times: dict[str, list[float]] = defaultdict(list)


def _prune_failures(bucket: list[float], now: float, window: int) -> None:
    cutoff = now - window
    while bucket and bucket[0] < cutoff:
        bucket.pop(0)


def check_login_rate_limit(key: str) -> bool:
    """Return True if `key` (username or IP) is currently locked out."""
    now = time.monotonic()
    if _login_lockuntil.get(key, 0.0) > now:
        return True
    bucket = _failed_login_attempts[key]
    _prune_failures(bucket, now, LOGIN_WINDOW_SECONDS)
    if len(bucket) >= LOGIN_MAX_FAILURES:
        _login_lockuntil[key] = now + LOGIN_LOCKOUT_SECONDS
        return True
    return False


def record_failed_login(key: str) -> None:
    now = time.monotonic()
    _prune_failures(_failed_login_attempts[key], now, LOGIN_WINDOW_SECONDS)
    _failed_login_attempts[key].append(now)


def reset_login_state(key: str) -> None:
    """Clear failure/lockout state for a key (called on successful login)."""
    _failed_login_attempts.pop(key, None)
    _login_lockuntil.pop(key, None)


def check_ip_login_rate_limit(client_ip: str) -> bool:
    """Return True if the IP exceeds the per-IP login rate window."""
    now = time.monotonic()
    bucket = _ip_login_times[client_ip]
    cutoff = now - LOGIN_IP_WINDOW_SECONDS
    while bucket and bucket[0] < cutoff:
        bucket.pop(0)
    return len(bucket) >= LOGIN_IP_MAX


def record_ip_login(client_ip: str) -> None:
    _ip_login_times[client_ip].append(time.monotonic())



class RefreshTokenRequest(BaseModel):
    """Body for POST /auth/refresh and /auth/logout-refresh."""

    refresh_token: str


def create_access_token(data: dict, expires_delta: Optional[datetime] = None) -> str:
    """Issue a signed JWT access token.

    Thin wrapper so other routers (e.g. ldap) can mint tokens without reaching
    into the service singleton directly. Delegates to ``auth_service`` so every
    token gets a unique ``jti`` (required for server-side revocation / logout).
    """
    return auth_service.create_access_token(data, expires_delta=expires_delta)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get current authenticated user.

    As part of establishing the request's authN/authZ context, this also resolves the
    *active tenant* (see ``app.services.tenant_scoping``). The raw ``X-Tenant-Id``
    header is forwarded to a request-scoped contextvar by ``ActiveTenantMiddleware``;
    here we resolve it: when the caller selected one of their tenants, that id is
    membership-validated and published to ``ACTIVE_TENANT_ID_CTX`` so every
    ``scope_current_tenant`` call in this request isolates to it. Without a header the
    contextvar stays at its default (``None``) and scoping falls back to the user's
    default tenant. Doing this here (rather than via a ``Request`` parameter) avoids a
    FastAPI quirk where a ``Request`` dependency silently breaks JSON body parsing for
    the whole route -- so no content endpoint or scoping helper needs changing.
    """
    payload = await auth_service.verify_token(db, token)
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

    # Findings #30: self-registered accounts must verify their email before they
    # can authenticate. Unverified users exist but cannot use their tokens yet.
    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Email address not verified")

    # Resolve the active tenant for this request (multi-tenant switching). Only query
    # membership when a specific tenant was requested, to avoid extra work on the
    # common no-header path. The raw header value comes from the middleware-provided
    # contextvar rather than a Request parameter.
    requested = get_requested_tenant_id()
    if requested is not None:
        try:
            tenant_id = int(requested)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400, detail=f"Invalid X-Tenant-Id header: {requested!r}"
            )
        allowed = await member_tenant_ids(db, user)
        if tenant_id not in allowed:
            raise HTTPException(
                status_code=403,
                detail="The current user is not a member of the requested tenant",
            )
        set_active_tenant_id(tenant_id)
    else:
        set_active_tenant_id(None)

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
    from app.models.auth import APIToken

    # L2 fix: verify API tokens with bcrypt instead of an unsalted SHA256 lookup.
    # The previous SHA256 approach could never match the bcrypt-stored
    # APIToken.token_hash values, silently breaking CMDB API-token auth; it also
    # stored/compared tokens with a fast, unsalted hash.
    # L4 fix (findings #4): look the token up by its HMAC index (single indexed
    # read) instead of bcrypt-verifying every active token, then confirm with one
    # cheap bcrypt check. This removes the O(n) per-request DoS surface.
    indexed = refresh_token_index(token)
    result = await db.execute(
        select(APIToken).where(
            APIToken.token_index == indexed,
            APIToken.is_active == True,
        )
    )
    api_token = result.scalar_one_or_none()
    if api_token is not None and pwd_context.verify(token, api_token.token_hash):
        if api_token.expires_at and _as_aware(api_token.expires_at) < _utcnow():
            raise HTTPException(status_code=401, detail="API token expired")
        permissions = [p.strip() for p in (api_token.permissions or "").split(",") if p.strip()]
        required_perm = "cmdb_write" if require_write else "cmdb_read"
        if required_perm not in permissions and "cmdb_all" not in permissions:
            raise HTTPException(status_code=403, detail=f"API token lacks '{required_perm}' permission")
        api_token.last_used_at = datetime.utcnow()
        await db.commit()
        user_stmt = select(User).where(User.id == api_token.user_id)
        user = (await db.execute(user_stmt)).scalar_one_or_none()
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User associated with token is inactive")
        return user

    # Not a valid API token — fall back to regular JWT auth (role-based)
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
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """Login and get access token (with brute-force protection, findings #6)."""
    # ``request`` is declared as ``= None`` rather than ``= Depends()`` on purpose:
    # FastAPI 0.163.1 fails to populate the OAuth2 form fields (spurious 422) when a
    # dependency is written ``request: Request = Depends()`` -- but a bare/defaulted
    # annotation injects the request normally, exactly like every other endpoint here.
    client_ip = request.client.host if request.client else (
        (request.headers.get("X-Forwarded-For").split(",")[0].strip())
        if request.headers.get("X-Forwarded-For") else "unknown"
    )

    # Reject early if the account or source IP is currently locked out / rate limited.
    if check_login_rate_limit(form_data.username) or check_ip_login_rate_limit(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again later.",
        )

    user = await auth_service.authenticate_user(db, form_data.username, form_data.password)

    if not user:
        record_failed_login(form_data.username)
        record_ip_login(client_ip)
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Success: clear any accumulated failures for this account/IP.
    reset_login_state(form_data.username)
    _ip_login_times[client_ip].clear()

    # Update last login
    user.last_login = datetime.utcnow()
    await db.commit()
    
    # Create access token
    access_token = auth_service.create_access_token(
        data={"sub": str(user.id), "role": user.role, "username": user.username}
    )

    # Issue a refresh token the client can use to mint new access tokens without
    # re-entering credentials (feature gap #1b: refresh-token rotation).
    refresh_token = await auth_service.issue_refresh_token(db, user.id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "full_name": user.full_name
        }
    }


@router.post("/auth/logout")
async def logout(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    """Server-side token revocation (logout).

    Records the token's ``jti`` in the revocation blocklist so it is rejected by
    :func:`get_current_user` until its ``exp`` passes — even though the JWT is
    still cryptographically valid. Idempotent: logging out an already-revoked
    (or expired) token is a harmless no-op.
    """
    payload = auth_service.decode_token(token)
    jti = payload.get("jti") if payload else None
    if jti:
        await auth_service.revoke_token(db, jti, reason="logout")
    return {"success": True, "message": "Logged out"}


@router.post("/auth/refresh")
async def refresh(body: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    """Exchange a refresh token for a new access (+ rotated) refresh token.

    Does not require a valid access token — that is the whole point. On any
    invalid/expired/leaked token we return 401 with a generic message so we do
    not leak which tokens are valid.
    """
    result = await auth_service.rotate_refresh_token(db, body.refresh_token)
    if result is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {
        "access_token": result["access_token"],
        "refresh_token": result["refresh_token"],
        "token_type": "bearer",
        "user": result["user"],
    }


@router.post("/auth/logout-refresh")
async def logout_refresh(body: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    """Revoke a single refresh token (sign out this device/session)."""
    revoked = await auth_service.revoke_single_refresh_token(db, body.refresh_token)
    return {"success": revoked, "message": "Refresh token revoked" if revoked else "No active refresh token to revoke"}


@router.post("/auth/logout-all")
async def logout_all(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Revoke every active refresh token for the current user (sign out everywhere)."""
    count = await auth_service.revoke_all_user_refresh_tokens(db, current_user.id)
    return {"success": True, "message": f"Revoked {count} refresh token(s)"}


@router.get("/auth/sessions")
async def list_sessions(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """List the current user's active refresh tokens (sessions)."""
    return {"sessions": await auth_service.list_active_refresh_tokens(db, current_user.id)}


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

    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")

    # pwd_context is imported at module level (native bcrypt via auth_service).
    if not pwd_context.verify(old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    current_user.password_hash = pwd_context.hash(new_password)
    # Invalidate every session/token issued before this moment (findings #2):
    # - access tokens: verify_token rejects any token with iat < password_changed_at
    # - refresh tokens: retire all active refresh tokens for the user
    # - API tokens: deactivate all of the user's API tokens
    current_user.password_changed_at = _utcnow()

    await auth_service.revoke_all_user_refresh_tokens(db, current_user.id)
    await db.execute(
        update(APIToken).where(APIToken.user_id == current_user.id).values(is_active=False)
    )
    await db.commit()

    return {"message": "Password changed successfully"}


# H1 fix: allowlist of roles a self-registering user can claim.
# Admins assign higher roles via the dedicated POST /auth/users endpoint (findings #31).
_ALLOWED_SELF_REGISTER_ROLES = frozenset({"user"})

# Roles an admin may directly assign when creating an account via POST /auth/users.
# These are the roles the system actually recognizes (see get_current_* dependencies).
_VALID_ADMIN_CREATED_ROLES = frozenset({"user", "staff", "developer", "admin", "cmdb_manager"})

# H8 fix: fields to exclude from custom_data on registration.
# The full JSON body was previously stored as-is, leaking password/role/email.
_RESERVED_REGISTRATION_FIELDS = frozenset({
    "username", "email", "password", "full_name", "role",
})


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
    """Register a new user (admin creates users, self-service defaults to 'user' role).

    H1 fix: role is validated against an allowlist; unknown roles default to 'user'.
    H8 fix: custom_data excludes reserved fields (password, role, email, username).
    """
    # Self-registration sends its data as query params; the JSON body is optional
    # and only used to collect extra custom_data fields. An absent/empty body (the
    # normal case) must not fail registration -- treat it as no extras.
    try:
        body = await request.json()
    except (json.JSONDecodeError, RuntimeError):
        body = {}
    if not isinstance(body, dict):
        body = {}

    # H1: validate role against allowlist -- unknown roles become "user"
    if role not in _ALLOWED_SELF_REGISTER_ROLES:
        role = "user"

    # H8: extract only non-reserved fields as custom_data
    custom_data = None
    if body:
        filtered = {k: v for k, v in body.items() if k not in _RESERVED_REGISTRATION_FIELDS}
        if filtered:
            custom_data = filtered

    try:
        user = await auth_service.create_user(
            db=db,
            username=username,
            email=email,
            password=password,
            role=role,
            full_name=full_name or username,
            custom_data=custom_data,
            is_verified=False,  # findings #30: self-registration starts unverified
        )

        # Findings #30: self-registration creates an *unverified* account. Email a
        # short-lived verification token so the caller can prove ownership before
        # the account can authenticate (get_current_user rejects unverified users).
        # Best-effort: registration still succeeds even if SMTP is unavailable.
        verification_token = auth_service.create_verification_token(user.id)
        # Reconstruct the app root from the request URL so the verification link is
        # absolute. `Request.url_root` / `.scheme` / `.netloc` were removed in newer
        # Starlette releases, so parse `request.url` (stable across versions) instead.
        _parsed_url = urlparse(str(request.url))
        base = f"{_parsed_url.scheme}://{_parsed_url.netloc}"
        verify_link = f"{base}/auth/verify-email?token={verification_token}"
        try:
            from app.services.email_service import send_email
            send_email(
                to=email,
                subject="Verify your PythonWorkflow account",
                body=(
                    "Welcome! Confirm your email address to activate your account:\n\n"
                    f"{verify_link}\n\nThis link expires in 24 hours."
                ),
            )
        except Exception as exc:  # never block registration on email delivery
            logger.warning("Failed to send verification email to %s: %s", email, exc)

        return {
            "message": "User created. Check your email to verify your account.",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "is_verified": user.is_verified
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/auth/users")
async def create_user_account(
    request: Request,
    username: str,
    email: str,
    password: str,
    full_name: Optional[str] = None,
    role: str = "user",
    admin_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: create a user account with an explicitly requested role.

    Findings #31: self-service ``register`` downgrades any role outside
    ``_ALLOWED_SELF_REGISTER_ROLES`` ({"user"}) to "user", so admins could not
    create staff/developer/admin accounts through it (the account was silently
    created as a restricted "user"). This endpoint requires an admin and honors
    the requested role directly. Admin-created accounts are trusted, so they start
    verified (is_verified=True) and can authenticate immediately.
    """
    if role not in _VALID_ADMIN_CREATED_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role {role!r}; allowed roles: {sorted(_VALID_ADMIN_CREATED_ROLES)}",
        )

    try:
        user = await auth_service.create_user(
            db=db,
            username=username,
            email=email,
            password=password,
            role=role,
            full_name=full_name or username,
            is_verified=True,  # admin-created accounts are trusted
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "message": "User created successfully",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "is_verified": user.is_verified,
        }
    }


@router.post("/auth/verify-email")
async def verify_email(
    token: str = Query(..., description="Verification token emailed at registration"),
    db: AsyncSession = Depends(get_db),
):
    """Confirm an email address using the token emailed at registration.

    Findings #30: self-registered accounts start unverified and cannot
    authenticate (get_current_user returns 403) until this endpoint sets
    ``is_verified=True``. The token is a signed JWT, so validation is
    stateless and does not require the revocation path.
    """
    payload = auth_service.decode_token(token)
    if not payload or payload.get("type") != "email_verification":
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=400, detail="Invalid verification token")
    try:
        user = await auth_service.get_user_by_id(db, int(user_id))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid verification token")
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_verified:
        return {"message": "Email already verified"}
    user.is_verified = True
    await db.commit()
    return {"message": "Email verified successfully"}


@router.get("/auth/me")
async def get_current_user_info(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user information, including the tenants they belong to.

    ``tenants`` lists every tenant the user is a member of (default + additional) so
    the frontend can render the tenant switcher. ``active_tenant_id`` is the tenant
    selected for this request (via the X-Tenant-Id header), or the user's default when
    none was requested.
    """
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "mfa_enabled": user.mfa_enabled,
        "groups": [{"id": g.id, "name": g.name} for g in user.groups],
        "tenants": list_member_tenants(db, user),
        "active_tenant_id": get_active_tenant_id(),
    }


@router.get("/auth/setup-required")
async def check_setup_required(db: AsyncSession = Depends(get_db)):
    """Check if setup is required (no users exist)"""
    from app.models.auth import User
    from sqlalchemy import select, update
    
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
    # Keys handled as explicit query params above. Anything else in the JSON
    # body is treated as custom_data, but these reserved keys must be stripped so
    # they are not silently persisted into custom_data and later echoed back by
    # list_users (findings #3).
    _RESERVED_UPDATE_KEYS = frozenset(
        {"email", "full_name", "role", "roles", "is_active", "mfa_enabled", "password"}
    )
    try:
        body = await request.json()
        if body:
            custom_data = {k: v for k, v in body.items() if k not in _RESERVED_UPDATE_KEYS}
        else:
            custom_data = None

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

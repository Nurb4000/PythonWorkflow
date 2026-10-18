"""
Authentication service for user management
"""
import hashlib
import hmac
import logging
import secrets
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
import bcrypt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.auth import User, Group, APIToken, TokenRevocation, RefreshToken
from app.core.config import settings

logger = logging.getLogger(__name__)

# Native bcrypt backend. passlib is dropped because bcrypt 4.x removed the
# low-level C API passlib depends on (it emits "(trapped) error reading bcrypt
# version" and can no longer detect the backend version). Hashing/verifying
# directly against `bcrypt` removes that fragility while staying fully
# compatible with existing `$2b$` hashes produced by passlib or any other tool.
BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # Malformed/None stored hash — mirrors passlib's verify() returning False.
        return False


class NativePwdContext:
    """Minimal CryptContext-compatible shim backed by native bcrypt.

    Exposes the same ``hash``/``verify`` surface the old passlib context did so
    call sites (and existing tests) can keep using ``pwd_context.hash(...)`` /
    ``pwd_context.verify(...)`` unchanged.
    """

    def hash(self, password: str) -> str:
        return _hash_password(password)

    def verify(self, password: str, hashed: str) -> bool:
        return _verify_password(password, hashed)


pwd_context = NativePwdContext()


def _utcnow() -> datetime:
    """Timezone-aware ``UTC now``.

    Postgres ``timestamptz`` columns round-trip as tz-aware datetimes, so all
    expiry comparisons must use an aware "now" — mixing in naive
    ``datetime.utcnow()`` raises ``TypeError`` (offset-naive vs offset-aware).
    """
    return datetime.now(timezone.utc)


def _as_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Coerce a possibly-naive datetime to tz-aware (treating naive as UTC).

    Postgres ``timestamptz`` columns *should* round-trip as aware, but this driver
    can return naive datetimes for values that were inserted as naive (e.g. the
    ``expires_at`` set by :meth:`create_api_token`). Comparing aware vs naive
    raises ``TypeError``, so both sides of an expiry check are normalized to aware
    before comparison — regardless of how the value was stored or loaded.
    """
    if dt is None or dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc) if dt is not None else None
    return dt

# Canonical set of role names. Used to validate role/roles writes so an
# administrator cannot introduce a rogue role or an inconsistent pair.
KNOWN_ROLES = frozenset({"admin", "developer", "cmdb_manager", "staff", "user"})


def refresh_token_index(raw_token: str) -> str:
    """Deterministic HMAC-SHA256 index of a plaintext refresh token.

    bcrypt() salts each hash, so the stored ``token_hash`` can't be used to look
    a presented token up by value. This stable index (tied to the app secret)
    enables indexed lookup and predecessor/successor linkage for rotation and
    replay detection without ever storing the plaintext.
    """
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        raw_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def reconcile_role_roles(role: Optional[str], roles: Optional[List[str]]) -> tuple[str, List[str]]:
    """Return a consistent (role, roles) pair where ``role == roles[0]``.

    I8 fix: the ``role`` scalar and ``roles`` array must never disagree. The
    primary role is authoritative:

    * If ``role`` is supplied it becomes ``roles[0]`` (and is prepended to any
      provided/existing ``roles``); if ``roles`` is not supplied it is derived
      as ``[role]``. This closes the demotion-bypass where an admin set
      ``role="user"`` while a stale ``"admin"`` lingered in ``roles`` and the
      OR-based ``has_role`` check still granted admin.
    * If only ``roles`` is supplied, ``roles[0]`` becomes the primary ``role``.
    * Every returned role is validated against :data:`KNOWN_ROLES`.
    """
    if role is not None and role not in KNOWN_ROLES:
        raise ValueError(f"Invalid role: {role!r}")

    if roles is not None:
        cleaned: List[str] = []
        for r in roles:
            if r not in cleaned:
                cleaned.append(r)
        for r in cleaned:
            if r not in KNOWN_ROLES:
                raise ValueError(f"Invalid role in roles list: {r!r}")
    else:
        cleaned = None

    if role is not None:
        # Primary role is authoritative: put it first, keep any extra roles.
        final_roles = [role] + [r for r in cleaned if r != role] if cleaned else [role]
    elif cleaned:
        # Only the array was provided; its first entry is the primary role.
        final_roles = cleaned
        role = cleaned[0]
    else:
        # Nothing supplied here — caller should not reach us with both None.
        final_roles = ["user"]
        role = "user"

    return role, final_roles


class AuthService:
    """Handle user authentication and authorization"""
    
    async def authenticate_user(self, db: AsyncSession, username: str, password: str) -> Optional[User]:
        """Authenticate user with username and password"""
        stmt = select(User).where(User.username == username)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            return None
        
        if not pwd_context.verify(password, user.password_hash):
            return None
        
        if not user.is_active:
            logger.warning(f"Inactive user attempted login: {username}")
            return None
        
        return user
    
    async def create_user(self, db: AsyncSession, username: str, email: str,
                          password: str, role: str = "user", full_name: str = "", custom_data: Optional[dict] = None) -> User:
        """Create a new user"""

        # Check if user exists
        stmt = select(User).where(User.username == username)
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            raise ValueError(f"Username '{username}' already exists")

        # Check for duplicate email
        stmt_email = select(User).where(User.email == email)
        result_email = await db.execute(stmt_email)
        if result_email.scalar_one_or_none():
            raise ValueError(f"Email '{email}' already exists")

        # Hash password
        password_hash = pwd_context.hash(password)

        # I8 fix: derive a consistent (role, roles) pair — primary role is
        # always roles[0], so the two fields can never disagree.
        role, roles = reconcile_role_roles(role or "user", None)

        user = User(
            username=username,
            email=email,
            password_hash=password_hash,
            role=role,
            roles=roles,
            full_name=full_name or username,
            is_active=True,
            is_verified=True,
            custom_data=custom_data or {}
        )
        
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        logger.info(f"Created user: {username} with role: {role}")
        return user
    
    async def update_user(self, db: AsyncSession, user_id: int, **kwargs) -> User:
        """Update user details"""
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise ValueError(f"User {user_id} not found")

        # I8 fix: reconcile the primary ``role`` scalar with the ``roles`` array
        # so they can never disagree. ``role`` is authoritative — setting it
        # derives ``roles`` (closing the demotion-bypass where a stale admin
        # entry lingered in ``roles``), and any provided ``roles`` must list the
        # primary role first.
        role = kwargs.pop("role", None)
        roles = kwargs.pop("roles", None)
        if role is not None or roles is not None:
            role, roles = reconcile_role_roles(role, roles)
            user.role = role
            user.roles = roles

        # Update remaining allowed fields
        allowed_fields = ['email', 'full_name', 'is_active', 'mfa_enabled']
        for field in allowed_fields:
            if field in kwargs:
                setattr(user, field, kwargs[field])

        if 'password' in kwargs and kwargs['password']:
            user.password_hash = pwd_context.hash(kwargs['password'])

        if 'custom_data' in kwargs and kwargs['custom_data'] is not None:
            current = user.custom_data or {}
            current.update(kwargs['custom_data'])
            user.custom_data = current
        
        await db.commit()
        await db.refresh(user)
        
        logger.info(f"Updated user: {user.username}")
        return user
    
    async def delete_user(self, db: AsyncSession, user_id: int) -> bool:
        """Deactivate a user (soft-delete)"""
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            return False

        user.is_active = False
        await db.commit()
        return True
    
    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create JWT access token.

        Each token carries a unique ``jti`` (JWT ID). Revocation (logout /
        refresh-token rotation) works by recording that ``jti`` in the
        ``token_revocations`` blocklist; see :meth:`verify_token`.
        """
        to_encode = data.copy()

        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)

        to_encode.update({"exp": expire, "jti": secrets.token_urlsafe(16)})
        encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
        return encoded_jwt

    def decode_token(self, token: str) -> Optional[dict]:
        """Pure JWT decode (signature + expiry). No revocation check.

        Returns the payload, or None if the token is missing/malformed/expired.
        """
        try:
            return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        except JWTError:
            return None

    async def is_token_revoked(self, db: AsyncSession, jti: Optional[str]) -> bool:
        """True if ``jti`` has been recorded in the revocation blocklist."""
        if not jti:
            return False
        stmt = select(TokenRevocation.id).where(TokenRevocation.jti == jti)
        result = await db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def verify_token(self, db: AsyncSession, token: str) -> Optional[dict]:
        """Verify a JWT: signature + expiry, then reject if revoked.

        This is the single choke point for access-token authentication; callers
        must go through it so revocation can never be bypassed. Returns the
        payload, or None if the token is invalid, expired, or revoked.
        """
        payload = self.decode_token(token)
        if payload is None:
            return None
        if await self.is_token_revoked(db, payload.get("jti")):
            return None
        return payload

    async def revoke_token(
        self,
        db: AsyncSession,
        jti: str,
        user_id: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> bool:
        """Record ``jti`` in the revocation blocklist (idempotent).

        Returns True if a row was written, False if one already existed.
        """
        if not jti:
            return False
        existing = await self.is_token_revoked(db, jti)
        if existing:
            return False
        rec = TokenRevocation(jti=jti, user_id=user_id, reason=reason)
        db.add(rec)
        await db.commit()
        return True

    async def issue_refresh_token(self, db: AsyncSession, user_id: int) -> str:
        """Create a fresh refresh token for a user and return its plaintext.

        Only the bcrypt hash and a deterministic HMAC index are persisted; the
        plaintext is shown to the client exactly once.
        """
        raw = secrets.token_urlsafe(32)
        now = _utcnow()
        db.add(
            RefreshToken(
                user_id=user_id,
                token_index=refresh_token_index(raw),
                token_hash=pwd_context.hash(raw),
                previous_token_index=None,
                expires_at=now + timedelta(days=settings.refresh_token_expire_days),
                is_active=True,
            )
        )
        await db.commit()
        return raw

    async def _get_refresh_by_index(self, db: AsyncSession, raw_token: str) -> Optional[RefreshToken]:
        stmt = select(RefreshToken).where(RefreshToken.token_index == refresh_token_index(raw_token))
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def rotate_refresh_token(
        self, db: AsyncSession, raw_token: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Exchange a valid refresh token for a new access + refresh pair.

        Implements RFC 8693-style rotation: a successor is issued that links back
        to the presented token via ``previous_token_index``. Because each token is
        single-use by construction, presenting the same token again is caught by
        the successor check -> a leak -> the whole chain is revoked and None is
        returned. Returns None for any invalid/expired/mismatched/revoked token so
        callers can answer 401 uniformly.
        """
        if not raw_token or not settings.refresh_token_rotation:
            return None

        presented = await self._get_refresh_by_index(db, raw_token)
        if presented is None or not presented.is_active or presented.expires_at < _utcnow():
            return None

        stored = presented.token_hash
        if not stored or not pwd_context.verify(raw_token, stored):
            return None

        user_row = await self.get_user_by_id(db, presented.user_id)
        if user_row is None or not user_row.is_active:
            return None

        # Leak / replay detection: an active successor means this token was
        # already rotated away yet is being presented again.
        succ_stmt = select(RefreshToken.id).where(
            RefreshToken.previous_token_index == presented.token_index,
            RefreshToken.is_active.is_(True),
        )
        succ = await db.execute(succ_stmt)
        if succ.scalar_one_or_none() is not None:
            await self.revoke_all_user_refresh_tokens(db, presented.user_id)
            logger.warning("Refresh-token replay/leak detected for user %s", presented.user_id)
            return None

        # Do NOT flip ``is_active`` here. Rotation is single-use by design: the
        # successor created below links back to this token, so presenting this
        # token again is caught by the leak check above and revokes the whole
        # chain. ``is_active`` is only cleared by explicit logout/revocation.
        new_raw = secrets.token_urlsafe(32)
        db.add(
            RefreshToken(
                user_id=presented.user_id,
                token_index=refresh_token_index(new_raw),
                token_hash=pwd_context.hash(new_raw),
                previous_token_index=presented.token_index,
                expires_at=_utcnow() + timedelta(days=settings.refresh_token_expire_days),
                is_active=True,
            )
        )
        await db.commit()

        access_token = self.create_access_token(
            data={"sub": str(user_row.id), "role": user_row.role, "username": user_row.username}
        )
        return {
            "access_token": access_token,
            "refresh_token": new_raw,
            "user": {"id": user_row.id, "username": user_row.username, "role": user_row.role},
        }

    async def revoke_single_refresh_token(self, db: AsyncSession, raw_token: Optional[str]) -> bool:
        """Retire a single refresh token (single-session logout)."""
        if not raw_token:
            return False
        presented = await self._get_refresh_by_index(db, raw_token)
        if presented is None or not presented.is_active:
            return False
        presented.is_active = False
        await db.commit()
        return True

    async def revoke_all_user_refresh_tokens(self, db: AsyncSession, user_id: int) -> int:
        """Retire every active refresh token for a user. Returns count revoked."""
        stmt = select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.is_active.is_(True)
        )
        result = await db.execute(stmt)
        records = result.scalars().all()
        for rec in records:
            rec.is_active = False
        if records:
            await db.commit()
        return len(records)

    async def list_active_refresh_tokens(self, db: AsyncSession, user_id: int) -> List[Dict[str, Any]]:
        """Return metadata for a user's *live* refresh tokens (session listing).

        A token is "live" while it is active, unexpired, and has not itself been
        rotated away (no active successor links back to it). Rotated-away parents
        stay ``is_active`` so their replay can be detected as a leak, but they must
        not appear as usable sessions here.
        """
        rotated_away = (
            select(RefreshToken.previous_token_index)
            .where(RefreshToken.is_active.is_(True), RefreshToken.previous_token_index.isnot(None))
            .scalar_subquery()
        )
        stmt = select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.is_active.is_(True),
            RefreshToken.expires_at > _utcnow(),
            RefreshToken.token_index.notin_(rotated_away),
        ).order_by(RefreshToken.created_at.desc())
        result = await db.execute(stmt)
        records = result.scalars().all()
        return [
            {
                "id": rec.id,
                "created_at": rec.created_at,
                "last_used_at": rec.last_used_at,
                "expires_at": rec.expires_at,
                "is_successor": rec.previous_token_index is not None,
            }
            for rec in records
        ]

    async def get_user_by_id(self, db: AsyncSession, user_id: int) -> Optional[User]:
        """Get user by ID with groups"""
        stmt = (
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.groups))
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_user_by_username(self, db: AsyncSession, username: str) -> Optional[User]:
        """Get user by username with groups"""
        stmt = (
            select(User)
            .where(User.username == username)
            .options(selectinload(User.groups))
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def list_users(self, db: AsyncSession, role: Optional[str] = None, 
                        is_active: Optional[bool] = None) -> List[User]:
        """List users with optional filters"""
        stmt = select(User).options(selectinload(User.groups))
        
        if role:
            stmt = stmt.where(User.role == role)
        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)
        
        result = await db.execute(stmt)
        return result.scalars().all()
    
    async def create_group(self, db: AsyncSession, name: str, description: str = "", 
                          group_type: str = "internal") -> Group:
        """Create a new group"""
        stmt = select(Group).where(Group.name == name)
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            raise ValueError(f"Group '{name}' already exists")
        
        group = Group(
            name=name,
            description=description,
            group_type=group_type,
            is_active=True
        )
        
        db.add(group)
        await db.commit()
        await db.refresh(group)
        
        logger.info(f"Created group: {name}")
        return group
    
    async def add_user_to_group(self, db: AsyncSession, user_id: int, group_id: int) -> bool:
        """Add user to group"""
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        stmt = select(Group).where(Group.id == group_id)
        result = await db.execute(stmt)
        group = result.scalar_one_or_none()
        
        if not group:
            raise ValueError(f"Group {group_id} not found")
        
        if group not in user.groups:
            user.groups.append(group)
            await db.commit()
        
        return True
    
    async def remove_user_from_group(self, db: AsyncSession, user_id: int, group_id: int) -> bool:
        """Remove user from group"""
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        stmt = select(Group).where(Group.id == group_id)
        result = await db.execute(stmt)
        group = result.scalar_one_or_none()
        
        if not group:
            raise ValueError(f"Group {group_id} not found")
        
        if group in user.groups:
            user.groups.remove(group)
            await db.commit()
        
        return True
    
    async def update_group(self, db: AsyncSession, group_id: int, **kwargs) -> Group:
        """Update group details (name, description, group_type, is_active)"""
        stmt = select(Group).where(Group.id == group_id)
        result = await db.execute(stmt)
        group = result.scalar_one_or_none()

        if not group:
            raise ValueError(f"Group {group_id} not found")

        allowed_fields = ['name', 'description', 'group_type', 'is_active']
        for field in allowed_fields:
            if field in kwargs:
                setattr(group, field, kwargs[field])

        await db.commit()
        await db.refresh(group)

        logger.info(f"Updated group: {group.name}")
        return group

    async def delete_group(self, db: AsyncSession, group_id: int) -> bool:
        """Deactivate a group (soft-delete)"""
        stmt = select(Group).where(Group.id == group_id)
        result = await db.execute(stmt)
        group = result.scalar_one_or_none()

        if not group:
            return False

        group.is_active = False
        await db.commit()
        return True

    async def set_user_groups(self, db: AsyncSession, user_id: int, group_ids: List[int]) -> User:
        """Replace the set of groups a user belongs to"""
        from sqlalchemy import delete, insert
        from app.models.auth import user_groups

        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise ValueError(f"User {user_id} not found")

        stmt = select(Group).where(Group.id.in_(group_ids))
        result = await db.execute(stmt)
        groups = result.scalars().all()

        if len(groups) != len(set(group_ids)):
            raise ValueError("One or more groups not found")

        await db.execute(delete(user_groups).where(user_groups.c.user_id == user_id))
        if group_ids:
            await db.execute(
                insert(user_groups),
                [{"user_id": user_id, "group_id": gid} for gid in group_ids]
            )
        await db.commit()
        await db.refresh(user, attribute_names=["groups"])
        return user

    async def list_groups(self, db: AsyncSession, include_inactive: bool = False) -> List[Group]:
        """List all groups with users"""
        stmt = select(Group).options(selectinload(Group.users))
        if not include_inactive:
            stmt = stmt.where(Group.is_active == True)
        result = await db.execute(stmt)
        return result.scalars().all()
    
    async def create_api_token(self, db: AsyncSession, user_id: int, name: str, 
                              permissions: List[str]) -> APIToken:
        """Create an API token for a user.

        L2 fix: uses bcrypt instead of unsalted SHA256 so that a DB breach
        doesn't allow offline brute-force of the raw tokens.
        """
        import secrets

        token = secrets.token_urlsafe(32)
        # bcrypt hash with automatic salt — much slower than SHA256,
        # making offline enumeration of stolen hashes practical only at small scale.
        token_hash = pwd_context.hash(token)
        
        api_token = APIToken(
            user_id=user_id,
            name=name,
            token_hash=token_hash,
            permissions=",".join(permissions),
            is_active=True,
            expires_at=datetime.utcnow() + timedelta(days=90)
        )
        
        db.add(api_token)
        await db.commit()
        await db.refresh(api_token)
        
        # Return the raw token (only shown once)
        return {"token": token, "api_token": api_token}
    
    async def verify_api_token(self, db: AsyncSession, token: str) -> Optional[User]:
        """Verify an API token and return the user.

        L2 fix: iterates active tokens and verifies each with bcrypt.
        Acceptable overhead since verification happens once per request.
        """
        stmt = select(APIToken).where(APIToken.is_active == True)
        result = await db.execute(stmt)
        api_tokens = result.scalars().all()

        api_token = None
        for t in api_tokens:
            if pwd_context.verify(token, t.token_hash):
                api_token = t
                break
        
        if not api_token:
            return None
        
        # Check expiration (expires_at is a timestamptz -> tz-aware; compare
        # against an aware "now" or Postgres-naive values raise TypeError).
        if api_token.expires_at and api_token.expires_at < _utcnow():
            return None
        
        # Update last used
        api_token.last_used_at = datetime.utcnow()
        await db.commit()
        
        # Get user
        stmt = select(User).where(User.id == api_token.user_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()


# Singleton instance
auth_service = AuthService()

"""
Authentication service for user management
"""
import logging
from typing import Optional, List
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.auth import User, Group, APIToken
from app.core.config import settings

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


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

        # Default roles to [role] if not specified
        roles = [role] if role else ["user"]

        user = User(
            username=username,
            email=email,
            password_hash=password_hash,
            role=role or "user",
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

        # Update allowed fields
        allowed_fields = ['email', 'full_name', 'role', 'roles', 'is_active', 'mfa_enabled']
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
        """Create JWT access token"""
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
        return encoded_jwt
    
    def verify_token(self, token: str) -> Optional[dict]:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
            return payload
        except JWTError:
            return None
    
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

        L2 fix: uses bcrypt (via passlib) instead of unsalted SHA256 so that
        a DB breach doesn't allow offline brute-force of the raw tokens.
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
        
        # Check expiration
        if api_token.expires_at and api_token.expires_at < datetime.utcnow():
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

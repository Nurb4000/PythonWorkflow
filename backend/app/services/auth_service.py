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
                          password: str, role: str = "user", full_name: str = "") -> User:
        """Create a new user"""
        
        # Check if user exists
        stmt = select(User).where(User.username == username)
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            raise ValueError(f"Username '{username}' already exists")
        
        # Hash password
        password_hash = pwd_context.hash(password)
        
        user = User(
            username=username,
            email=email,
            password_hash=password_hash,
            role=role,
            full_name=full_name or username,
            is_active=True,
            is_verified=True  # Auto-verify for internal auth
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
        allowed_fields = ['email', 'full_name', 'role', 'is_active', 'mfa_enabled']
        for field in allowed_fields:
            if field in kwargs:
                setattr(user, field, kwargs[field])
        
        await db.commit()
        await db.refresh(user)
        
        logger.info(f"Updated user: {user.username}")
        return user
    
    async def delete_user(self, db: AsyncSession, user_id: int) -> bool:
        """Delete a user"""
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            return False
        
        await db.delete(user)
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
        stmt = select(User)
        
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
    
    async def list_groups(self, db: AsyncSession) -> List[Group]:
        """List all groups with users"""
        stmt = select(Group).options(selectinload(Group.users))
        result = await db.execute(stmt)
        return result.scalars().all()
    
    async def create_api_token(self, db: AsyncSession, user_id: int, name: str, 
                              permissions: List[str]) -> APIToken:
        """Create an API token for a user"""
        import hashlib
        import secrets
        
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        
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
        """Verify an API token and return the user"""
        import hashlib
        
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        
        stmt = select(APIToken).where(APIToken.token_hash == token_hash, APIToken.is_active == True)
        result = await db.execute(stmt)
        api_token = result.scalar_one_or_none()
        
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

#!/usr/bin/env python3
"""
Setup script to create initial admin user
Run this once to set up your first admin account
"""
import asyncio
import sys
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Add backend to path
sys.path.insert(0, "backend")

from app.core.database import Base, engine
from app.models.auth import User
from app.services.auth_service import auth_service
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def setup_admin():
    """Create initial admin user"""
    
    # Create tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with AsyncSession(engine) as db:
        # Check if admin already exists
        stmt = User.__table__.select().where(User.username == "admin")
        result = await db.execute(stmt)
        existing = result.fetchone()
        
        if existing:
            print("Admin user already exists!")
            return
        
        # Create admin user
        admin_user = await auth_service.create_user(
            db=db,
            username="admin",
            email="admin@example.com",
            password="admin123",  # Change this!
            role="admin",
            full_name="Administrator"
        )
        
        print(f"✓ Admin user created!")
        print(f"  Username: admin")
        print(f"  Password: admin123")
        print(f"  Email: admin@example.com")
        print(f"\n⚠️  IMPORTANT: Change the password after first login!")
        
        await db.commit()


if __name__ == "__main__":
    asyncio.run(setup_admin())

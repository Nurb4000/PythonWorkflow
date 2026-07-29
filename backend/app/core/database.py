"""
Database connection and session management
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

# Ensure database directory exists
db_path = "backend_data"
os.makedirs(db_path, exist_ok=True)

# Create async engine
if settings.database_url.startswith("sqlite"):
    # For SQLite, use absolute path
    db_url = f"sqlite+aiosqlite:///{os.path.join(db_path, 'workflow.db')}"
    engine = create_async_engine(db_url, echo=settings.debug)
else:
    engine = create_async_engine(settings.database_url, echo=settings.debug)

# Session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """Dependency for getting database sessions"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Close database connection"""
    await engine.dispose()

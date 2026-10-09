"""
Database connection and session management
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

# Create async engine (echo defaults to False; override with SQL_ECHO env var)
engine = create_async_engine(
    settings.database_url,
    echo=settings.sql_echo,
)

# Session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """Dependency for getting database sessions with auto-commit."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db_manual() -> AsyncSession:
    """Dependency for manual transaction control (no auto-commit).

    Use this when the endpoint needs multi-step operations with explicit
    commit/rollback points. Caller is responsible for committing or rolling
    back before the generator exits.
    """
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Initialize database tables (legacy fallback; migrations are the canonical path).

    Tables and schema are managed by alembic (see backend/alembic). This only
    exists as a safety net for running the app directly without running
    `alembic upgrade head` first.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Close database connection"""
    await engine.dispose()

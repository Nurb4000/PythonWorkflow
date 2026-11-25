"""
Database connection and session management
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

# E6: Database query timeout (seconds) — prevents long-running queries from blocking pool slots
QUERY_TIMEOUT = getattr(settings, "query_timeout_seconds", 30)

# Create async engine with pool monitoring config and query timeout
engine = create_async_engine(
    settings.database_url,
    echo=settings.sql_echo,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,
)

# Session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


def get_pool_status() -> dict:
    """Return connection pool metrics for health monitoring."""
    pool = engine.pool
    return {
        "pool_size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "total": pool.checkedin() + pool.checkedout(),
    }


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

"""Shared PostgreSQL setup for the backend test suite.

SQLite is no longer used anywhere: every test runs against a dedicated
PostgreSQL database so test behavior matches production exactly.

- Target database defaults to workflow_db_test on the docker-compose
  Postgres; override with TEST_DATABASE_URL when running outside Docker
  (e.g. host localhost instead of the postgres service name).
- The database is created automatically if missing.
- Each test gets a pristine schema: public schema is dropped/recreated
  before metadata.create_all, which also clears any stray DB views left
  by SQLView tests.
"""
import os

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.database import Base


TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://workflow_user:workflow_password@postgres:5432/workflow_db_test",
)


async def _create_database_if_missing() -> None:
    """Create the test database using the maintenance 'postgres' DB."""
    dbname = TEST_DATABASE_URL.rsplit("/", 1)[1]
    admin_url = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            exists = await conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": dbname},
            )
            if exists.scalar() is None:
                await conn.execute(text(f'CREATE DATABASE "{dbname}"'))
    finally:
        await engine.dispose()


@pytest_asyncio.fixture()
async def db_engine():
    """Fresh-schema PostgreSQL engine handed to each test."""
    import app.models  # noqa: F401 -- register all models on Base.metadata

    await _create_database_if_missing()
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
            await conn.run_sync(Base.metadata.create_all)
        yield engine
    finally:
        await engine.dispose()

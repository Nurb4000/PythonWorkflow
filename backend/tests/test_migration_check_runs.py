"""
Regression test for I7: _check_migrations no longer silently swallows a
NameError.

Previously ``_check_migrations`` referenced an undefined ``engine`` name; the
bare ``except`` turned that into a silent no-op, so the startup migration check
never ran. This test stubs the alembic + engine pieces and asserts the function
actually executes the DB connection / migration-context path (surfacing a
migration-behind warning) instead of raising/swallowing internally.
"""
import asyncio
from unittest import mock

import app.main as main
from app.main import _check_migrations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import AsyncEngine


def test_check_migrations_executes_connection_path(caplog):
    class FakeCtx:
        def get_current_revision(self):
            return "stale_rev"  # differs from head -> triggers the warning branch

    class FakeConn:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def configure(self, *args, **kwargs):
            return FakeCtx()

    def fake_connect(self):
        return FakeConn()

    class FakeScript:
        def get_current_head(self):
            return "head_rev"

    def fake_from_config(cfg):
        return FakeScript()

    def fake_configure(conn):
        return FakeCtx()

    # engine.connect is read-only on the instance, so patch via mock; the two
    # alembic classmethods are patched manually and restored in finally.
    orig_from_config = ScriptDirectory.from_config
    orig_configure = MigrationContext.configure
    ScriptDirectory.from_config = staticmethod(fake_from_config)
    MigrationContext.configure = staticmethod(fake_configure)
    try:
        with mock.patch.object(AsyncEngine, "connect", fake_connect):
            with caplog.at_level("WARNING"):
                asyncio.run(_check_migrations())
    finally:
        ScriptDirectory.from_config = orig_from_config
        MigrationContext.configure = orig_configure

    assert "Database migration behind" in caplog.text
    assert "stale_rev" in caplog.text
    assert "head_rev" in caplog.text

"""
Regression tests for findings #7 (bootstrap admin password only logged masked ->
operational lock-out risk).

Problem: on first run the app created a high-entropy random admin password and logged
it only *masked* (`first4****last4`). If that startup log was never captured/retained,
the operator had no way to obtain the credentials -> permanent lock-out.

Fix (findings #7): the plaintext bootstrap password is persisted encrypted-at-rest in
``system_settings.bootstrap_admin_password`` (Fernet, keyed off SECRET_KEY — same
mechanism as findings #34), so it survives a lost/unretained startup log. It is
retrievable later via ``scripts/setup_admin.py --show`` and regenerable via
``--reset``. Because it lives in ``system_settings`` (not a user record echoed by any
user endpoint) there is no new API leak.

These tests are self-contained: in-memory SQLite (StaticPool) with the real
``SystemSetting``/``User`` tables, so no live PostgreSQL is required.
"""
import os
import sys

# Make the repo-root `scripts/` package importable (repo root is 3 levels up from
# this file: backend/tests/<this file>). `app` is already importable via backend/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.system_settings import SystemSetting
from app.models.auth import User
from app.utils.secret_encryption import SECRET_SETTING_KEYS


@pytest.fixture()
async def sqlite():
    """In-memory SQLite with system_settings + users tables; returns a factory."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[SystemSetting.__table__, User.__table__],
        )

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _add_admin(db):
    """Insert an admin user directly (avoids bcrypt cost; cmd_show only checks existence)."""
    from app.services.auth_service import pwd_context

    db.add(User(
        username="admin",
        email="admin@example.com",
        role="admin",
        password_hash=pwd_context.hash("test-password"),
    ))
    await db.commit()


# --- persistence: encrypted at rest, retrievable --------------------------------

async def test_bootstrap_password_key_is_encrypted_at_rest(sqlite):
    """The bootstrap key is in SECRET_SETTING_KEYS, so set_setting encrypts it."""
    assert "bootstrap_admin_password" in SECRET_SETTING_KEYS

    from app.api.system_settings import set_setting, get_setting
    from app.utils.secret_encryption import decrypt_secret

    pw = "s3cr3t-bootstrap-pw"
    async with sqlite() as db:
        await set_setting(db, "bootstrap_admin_password", pw)

    # Stored value differs from plaintext (encrypted at rest).
    async with sqlite() as db:
        row = (await db.execute(
            select(SystemSetting).where(SystemSetting.key == "bootstrap_admin_password"))
        ).scalar_one()
        assert row.value != pw

    # Retrievable via the documented read path: decrypt_secret(get_setting(...)).
    async with sqlite() as db:
        assert decrypt_secret(await get_setting(db, "bootstrap_admin_password")) == pw


async def test_bootstrap_password_not_stored_cleartext(sqlite):
    """The plaintext must not appear verbatim in the stored row."""
    from app.api.system_settings import set_setting

    pw = "correct-horse-battery-staple"
    async with sqlite() as db:
        await set_setting(db, "bootstrap_admin_password", pw)
        row = (await db.execute(
            select(SystemSetting).where(SystemSetting.key == "bootstrap_admin_password"))
        ).scalar_one()
    assert pw not in row.value  # ciphertext, not cleartext


# --- scripts/setup_admin.py --show / --reset ------------------------------------

async def test_cmd_show_retrieves_persisted_password(sqlite, capsys):
    """`--show` prints the persisted bootstrap password (findings #7)."""
    from app.api.system_settings import set_setting
    from scripts import setup_admin

    async with sqlite() as db:
        await _add_admin(db)
        await set_setting(db, "bootstrap_admin_password", "retrieve-me-123")

    rc = await setup_admin.cmd_show(db)

    assert rc == 0
    out = capsys.readouterr().out
    assert "retrieve-me-123" in out
    assert "Bootstrap admin password" in out


async def test_cmd_show_when_not_persisted_returns_1(sqlite, capsys):
    """`--show` fails cleanly (exit 1) if the password was never persisted."""
    from scripts import setup_admin

    async with sqlite() as db:
        await _add_admin(db)  # admin exists, but no persisted password
        rc = await setup_admin.cmd_show(db)

    assert rc == 1
    out = capsys.readouterr().out
    assert "no persisted" in out.lower()
    assert "--reset" in out


async def test_cmd_reset_regenerates_and_persists(sqlite, capsys):
    """`--reset` sets a new password that is then retrievable via `--show`."""
    from app.api.system_settings import get_setting
    from app.utils.secret_encryption import decrypt_secret
    from scripts import setup_admin

    async with sqlite() as db:
        await _add_admin(db)
        rc = await setup_admin.cmd_reset(db)

    assert rc == 0
    new_pw = capsys.readouterr().out.split("New password: ")[1].splitlines()[0].strip()

    # The new password is persisted and retrievable.
    async with sqlite() as db:
        assert decrypt_secret(await get_setting(db, "bootstrap_admin_password")) == new_pw

    # And --show now succeeds.
    async with sqlite() as db:
        rc2 = await setup_admin.cmd_show(db)
    assert rc2 == 0


async def test_create_admin_persists_password(sqlite, capsys):
    """`_create_admin` (default path) creates the admin and persists its password."""
    from app.api.system_settings import get_setting
    from app.utils.secret_encryption import decrypt_secret
    from scripts import setup_admin

    async with sqlite() as db:
        created_pw = await setup_admin._create_admin(db)

    assert created_pw  # returns the generated password

    # Admin user was created.
    async with sqlite() as db:
        admin = (await db.execute(select(User).where(User.username == "admin"))).scalar_one()
    assert admin is not None

    # The plaintext password is persisted and retrievable.
    async with sqlite() as db:
        assert decrypt_secret(await get_setting(db, "bootstrap_admin_password")) == created_pw


async def test_default_create_when_already_exists_is_idempotent(sqlite, capsys):
    """Running the default command again reports existence instead of duplicating."""
    from scripts import setup_admin

    async with sqlite() as db:
        await _add_admin(db)
        rc = await setup_admin.cmd_create(db)

    assert rc == 0
    out = capsys.readouterr().out
    assert "already exists" in out.lower()
    # Still exactly one admin.
    async with sqlite() as db:
        count = (await db.execute(select(User).where(User.role == "admin"))).scalar_one()
    assert count is not None

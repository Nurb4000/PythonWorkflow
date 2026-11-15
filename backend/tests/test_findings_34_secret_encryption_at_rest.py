"""
Regression tests for findings #34 (SMTP/IMAP/LDAP credentials stored in plaintext).

Credentials were persisted as cleartext key/value rows in ``system_settings``. A DB
compromise (or an over-privileged endpoint) therefore yielded plaintext SMTP/IMAP/
LDAP bind passwords.

Fix (findings #34): credentials are encrypted at rest via Fernet, keyed off the
process SECRET_KEY. Writes funnel through ``set_setting`` (encrypts credential
keys); the internal read sites decrypt them back to plaintext for runtime use.
GET endpoints already mask these values, so there is no new API leak.

These tests are self-contained: they use an in-memory SQLite DB (StaticPool) with
the real ``SystemSetting`` table and monkeypatch the session factory the load
functions import, so no live PostgreSQL is required.
"""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.system_settings import SystemSetting
from app.utils.secret_encryption import (
    SECRET_SETTING_KEYS,
    encrypt_secret,
    decrypt_secret,
)


@pytest.fixture()
async def sqlite():
    """In-memory SQLite with just the system_settings table; returns a factory."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[SystemSetting.__table__])

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


# --- pure encrypt/decrypt roundtrip --------------------------------------------

def test_encrypt_decrypt_roundtrip():
    for secret in ["s3cr3t", "p@ss w/rd + spaces", "unicode_ñ_✓"]:
        token = encrypt_secret(secret)
        assert token != secret  # stored value differs from plaintext
        assert decrypt_secret(token) == secret
    # Empty input roundtrips to empty (nothing to store).
    assert encrypt_secret("") == ""
    assert decrypt_secret("") == ""


def test_encrypt_empty_returns_empty():
    assert encrypt_secret("") == ""
    assert decrypt_secret("") == ""
    assert decrypt_secret(None) == ""


# --- set_setting encrypts credentials, stores non-secrets plainly --------------

async def test_set_setting_encrypts_credentials_and_stores_plain_others(sqlite):
    factory = sqlite
    async with factory() as db:
        from app.api.system_settings import set_setting
        await set_setting(db, "smtp_password", "smtp-secret")
        await set_setting(db, "imap_password", "imap-secret")
        await set_setting(db, "smtp_host", "smtp.example.com")
        await set_setting(db, "smtp_port", "465")
        await db.commit()

        rows = {r.key: r.value for r in (
            await db.execute(select(SystemSetting))).scalars().all()}

    # Secrets are stored encrypted (differ from plaintext).
    assert rows["smtp_password"] != "smtp-secret"
    assert rows["imap_password"] != "imap-secret"
    # Non-secret settings are stored unchanged.
    assert rows["smtp_host"] == "smtp.example.com"
    assert rows["smtp_port"] == "465"

    # And the encrypted secrets decrypt back to the originals.
    assert decrypt_secret(rows["smtp_password"]) == "smtp-secret"
    assert decrypt_secret(rows["imap_password"]) == "imap-secret"


async def test_credential_keys_are_exactly_the_secrets():
    assert SECRET_SETTING_KEYS == {"smtp_password", "imap_password", "ldap_bind_password"}


# --- read sites decrypt stored secrets -----------------------------------------

async def test_load_smtp_overrides_decrypts_stored_password(sqlite, monkeypatch):
    import app.core.database as database_mod
    from app.api.system_settings import set_setting
    from app.services import email_service
    from app.core.config import settings as app_settings

    # Write via the real (encrypting) write path, then confirm ciphertext is stored.
    async with sqlite() as db:
        await set_setting(db, "smtp_password", "smtp-secret")
    async with sqlite() as db:
        row = (await db.execute(
            select(SystemSetting).where(SystemSetting.key == "smtp_password"))).scalar_one()
        assert row.value != "smtp-secret"

    monkeypatch.setattr(database_mod, "async_session_factory", sqlite)
    app_settings.smtp_password = ""  # reset runtime field
    await email_service.load_smtp_overrides()

    assert app_settings.smtp_password == "smtp-secret"


async def test_load_ldap_overrides_decrypts_stored_password(sqlite, monkeypatch):
    import app.core.database as database_mod
    from app.api.system_settings import set_setting
    from app.services import ldap_service
    from app.core.config import settings as app_settings

    async with sqlite() as db:
        await set_setting(db, "ldap_bind_password", "ldap-secret")
    async with sqlite() as db:
        row = (await db.execute(
            select(SystemSetting).where(SystemSetting.key == "ldap_bind_password"))).scalar_one()
        assert row.value != "ldap-secret"

    monkeypatch.setattr(database_mod, "async_session_factory", sqlite)
    app_settings.ldap_bind_password = ""  # reset runtime field
    await ldap_service.load_ldap_overrides()

    assert app_settings.ldap_bind_password == "ldap-secret"


async def test_email_monitor_load_settings_decrypts_imap_password(sqlite, monkeypatch):
    from app.api.system_settings import set_setting
    from app.services import email_monitor

    async with sqlite() as db:
        await set_setting(db, "imap_password", "imap-secret")
    async with sqlite() as db:
        row = (await db.execute(
            select(SystemSetting).where(SystemSetting.key == "imap_password"))).scalar_one()
        assert row.value != "imap-secret"

    monkeypatch.setattr(email_monitor, "async_session_factory", sqlite)
    cls = email_monitor.EmailMonitorService
    inst = cls.__new__(cls)
    inst._settings_cache = {}
    monkeypatch.setattr(inst, "_load_settings", cls._load_settings.__get__(inst))
    await inst._load_settings()

    assert inst._settings_cache.get("imap_password") == "imap-secret"

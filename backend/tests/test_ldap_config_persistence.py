"""
Regression tests for M9: LDAP config persistence + bind-password handling.

Verifies that:
  * LDAP config (including the bind password) is persisted to the
    system_settings table and re-applied onto runtime settings at startup via
    ``load_ldap_overrides`` (so it survives restarts), and
  * the GET /admin/ldap/config response never exposes the bind password.
"""
from types import SimpleNamespace

import pytest_asyncio

from app.api.system_settings import set_setting
from app.services.ldap_service import load_ldap_overrides
from app.core.config import settings


@pytest_asyncio.fixture
async def _clean_ldap_settings(db_session):
    """Clear any persisted LDAP keys before/after the test."""
    from sqlalchemy import select
    from app.models.system_settings import SystemSetting

    keys = ("ldap_server_url", "ldap_base_dn", "ldap_bind_dn",
            "ldap_bind_password", "ldap_user_filter", "ldap_username_attribute",
            "ldap_email_attribute", "ldap_fullname_attribute",
            "ldap_sync_enabled", "ldap_sync_interval_hours")
    await db_session.execute(
        select(SystemSetting).where(SystemSetting.key.in_(keys))
    )
    rows = (await db_session.execute(select(SystemSetting).where(SystemSetting.key.in_(keys)))).scalars().all()
    for r in rows:
        await db_session.delete(r)
    await db_session.commit()
    yield
    for r in (await db_session.execute(select(SystemSetting).where(SystemSetting.key.in_(keys)))).scalars().all():
        await db_session.delete(r)
    await db_session.commit()


async def test_load_ldap_overrides_applies_persisted_config(_clean_ldap_settings, db_session):
    await set_setting(db_session, "ldap_server_url", "ldap://dc.example.com")
    await set_setting(db_session, "ldap_base_dn", "dc=example,dc=com")
    await set_setting(db_session, "ldap_bind_dn", "cn=service,ou=Users,dc=example,dc=com")
    await set_setting(db_session, "ldap_bind_password", "super-secret-bind-pw")
    await set_setting(db_session, "ldap_sync_enabled", "true")
    await set_setting(db_session, "ldap_sync_interval_hours", "6")

    await load_ldap_overrides()

    assert settings.ldap_server_url == "ldap://dc.example.com"
    assert settings.ldap_base_dn == "dc=example,dc=com"
    assert settings.ldap_bind_dn == "cn=service,ou=Users,dc=example,dc=com"
    assert settings.ldap_bind_password == "super-secret-bind-pw"
    assert settings.ldap_sync_enabled is True
    assert settings.ldap_sync_interval_hours == 6


async def test_get_config_does_not_expose_bind_password(_clean_ldap_settings, db_session):
    from app.api.ldap import get_ldap_config

    await set_setting(db_session, "ldap_bind_password", "super-secret-bind-pw")
    await load_ldap_overrides()

    admin = SimpleNamespace(id=1, role="admin", groups=[])
    resp = await get_ldap_config(current_user=admin, db=db_session)

    assert "ldap_bind_password" not in resp
    assert resp["ldap_server_url"] == "ldap://dc.example.com"

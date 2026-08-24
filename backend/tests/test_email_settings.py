"""
Tests for outgoing email settings + the real test-email endpoint:

- update_email_settings writes to the REAL smtp_* config fields (the old
  endpoint wrote email_smtp_* fields that never existed) and persists
  overrides to system_settings
- get_settings exposes effective (non-secret) SMTP configuration
- send_test_email returns stage-level diagnostics: ok path and per-stage
  failures (connect/starttls/login/send/config)

Suite convention: API functions called directly with a stub principal.
smtplib.SMTP is monkeypatched with a fake server; no network is touched.
"""
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.system_settings import (
    get_settings,
    update_email_settings,
    test_email as api_test_email,
)
from app.core.config import settings as app_settings
from app.models.system_settings import SystemSetting
from app.services import email_service


@pytest_asyncio.fixture
async def session(db_engine):
    async with async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)() as s:
        yield s


@pytest.fixture
def user():
    return SimpleNamespace(id=1, role="admin", username="tester")


@pytest.fixture(autouse=True)
def clean_smtp_config(monkeypatch):
    """Isolate the global settings object for every test."""
    for key, value in [
        ("smtp_host", ""), ("smtp_port", 587), ("smtp_username", ""),
        ("smtp_password", ""), ("smtp_from", "no-reply@test.local"), ("smtp_tls", True),
    ]:
        monkeypatch.setattr(app_settings, key, value, raising=False)
    yield


def _fake_smtp(monkeypatch, fail_stage: str | None = None):
    """Patch smtplib.SMTP with a scripted fake. Records calls on instance."""
    calls = {"starttls": False, "login": None, "sent": []}

    class FakeSMTP:
        def __init__(self, host, port, timeout=10):
            if fail_stage == "connect":
                raise ConnectionRefusedError(f"cannot reach {host}:{port}")
            self.host, self.port = host, port

        def starttls(self):
            if fail_stage == "starttls":
                raise RuntimeError("STARTTLS not supported by server")
            calls["starttls"] = True

        def login(self, user, password):
            if fail_stage == "login":
                raise RuntimeError("535 authentication failed")
            calls["login"] = user

        def send_message(self, msg):
            if fail_stage == "send":
                raise RuntimeError("recipient rejected")
            calls["sent"].append(msg["To"])

        def quit(self):
            pass

    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    return calls


class TestUpdateEmailSettings:
    @pytest.mark.asyncio
    async def test_writes_real_fields_and_persists(self, session, user):
        resp = await update_email_settings(
            smtp_host="smtp.example.com", smtp_port=465, username="mailer",
            password="secret", from_address="wf@example.com", smtp_tls=False,
            current_user=user, db=session,
        )
        assert app_settings.smtp_host == "smtp.example.com"
        assert app_settings.smtp_port == 465
        assert app_settings.smtp_username == "mailer"
        assert app_settings.smtp_password == "secret"
        assert app_settings.smtp_from == "wf@example.com"
        assert app_settings.smtp_tls is False

        rows = {r.key: r.value for r in (
            await session.execute(select(SystemSetting))).scalars().all()}
        assert rows["smtp_host"] == "smtp.example.com"
        assert rows["smtp_port"] == "465"
        assert rows["smtp_tls"] == "false"
        assert rows["smtp_password"] == "secret"
        assert resp["message"] == "Email settings updated"

    @pytest.mark.asyncio
    async def test_empty_password_keeps_existing(self, session, user):
        await update_email_settings(
            smtp_host="h", username="u", password="first",
            current_user=user, db=session,
        )
        await update_email_settings(
            smtp_host="h2", username="u", password="",
            current_user=user, db=session,
        )
        assert app_settings.smtp_password == "first"

    @pytest.mark.asyncio
    async def test_rejects_non_admin(self, session):
        staffer = SimpleNamespace(id=2, role="staff", username="s")
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await update_email_settings(smtp_host="h", current_user=staffer, db=session)
        assert exc.value.status_code == 403


class TestGetSettings:
    @pytest.mark.asyncio
    async def test_returns_effective_non_secret_fields(self, user):
        app_settings.smtp_host = "mail.test"
        app_settings.smtp_username = "u"
        app_settings.smtp_tls = False
        data = await get_settings(current_user=user)
        assert data["smtp_host"] == "mail.test"
        assert data["smtp_username"] == "u"
        assert data["smtp_tls"] is False
        assert "smtp_password" not in data


class TestSendTestEmail:
    @pytest.mark.asyncio
    async def test_unconfigured_reports_config_stage(self, user):
        result = await api_test_email(to_email="a@b.c", current_user=user)
        assert result["ok"] is False
        assert result["stage"] == "config"

    @pytest.mark.asyncio
    async def test_success_path(self, user, monkeypatch):
        app_settings.smtp_host = "mail.test"
        calls = _fake_smtp(monkeypatch)
        result = await api_test_email(to_email="dest@b.c", current_user=user)
        assert result["ok"] is True
        assert result["stage"] is None
        assert calls["sent"] == ["dest@b.c"]
        assert result["host"] == "mail.test"
        assert result["username_configured"] is False

    @pytest.mark.asyncio
    async def test_connect_failure_reports_stage_and_error(self, user, monkeypatch):
        app_settings.smtp_host = "dead.mail"
        _fake_smtp(monkeypatch, fail_stage="connect")
        result = await api_test_email(to_email="a@b.c", current_user=user)
        assert result["ok"] is False
        assert result["stage"] == "connect"
        assert "ConnectionRefusedError" in result["error"]

    @pytest.mark.asyncio
    async def test_send_failure_reports_stage(self, user, monkeypatch):
        app_settings.smtp_host = "mail.test"
        _fake_smtp(monkeypatch, fail_stage="send")
        result = await api_test_email(to_email="a@b.c", current_user=user)
        assert result["ok"] is False
        assert result["stage"] == "send"
        assert "recipient rejected" in result["error"]

    @pytest.mark.asyncio
    async def test_requires_admin(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await api_test_email(to_email="a@b.c", current_user=SimpleNamespace(id=3, role="user"))
        assert exc.value.status_code == 403


class TestLoadSmtpOverrides:
    @pytest.mark.asyncio
    async def test_overrides_applied_at_startup(self, db_engine, monkeypatch):
        async with async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)() as s:
            for key, value in [("smtp_host", "db.mail"), ("smtp_port", "2525"), ("smtp_tls", "false")]:
                s.add(SystemSetting(key=key, value=value))
            await s.commit()

        # Point load_smtp_overrides at this engine's session factory (the
        # function imports it from app.core.database at call time)
        import app.core.database as database_mod
        factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
        monkeypatch.setattr(database_mod, "async_session_factory", factory)

        await email_service.load_smtp_overrides()
        assert app_settings.smtp_host == "db.mail"
        assert app_settings.smtp_port == 2525
        assert app_settings.smtp_tls is False

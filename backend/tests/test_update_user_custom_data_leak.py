"""
Regression tests for findings #3: ``update_user`` must not persist the whole
request body into ``custom_data``. Reserved keys handled as explicit query
params (email, full_name, role, roles, is_active, mfa_enabled, password) are
stripped so they cannot be silently stored and later echoed back by list_users.

The test patches ``auth_service.update_user`` and inspects the ``custom_data``
kwarg the endpoint forwards, so it verifies the stripping behavior without a
live PostgreSQL (the shared ``db_session`` fixture is unavailable in this env).
"""
import pytest

from app.services.auth_service import auth_service
from unittest.mock import patch


class _Req:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


def _fake_update(captured):
    async def fake_update(db, user_id, **kwargs):
        captured.update(kwargs)

        class _U:
            id = user_id
            username = "u"
            email = "u@u.test"
            full_name = "U"
            role = "user"
            roles = []
            is_active = True

        return _U()
    return fake_update


@pytest.mark.asyncio
async def test_update_user_strips_reserved_keys_from_custom_data():
    """Reserved keys are removed from custom_data; genuinely custom fields remain."""
    captured = {}
    with patch.object(auth_service, "update_user", side_effect=_fake_update(captured)):
        from app.api.auth import update_user

        admin = type("Admin", (), {"id": 1})()
        req = _Req({"password": "s3cret", "role": "staff", "department": "ops"})
        await update_user(req, user_id=7, role="staff", admin_user=admin, db=None)

    assert "password" not in captured["custom_data"]
    assert "role" not in captured["custom_data"]
    assert captured["custom_data"].get("department") == "ops"


@pytest.mark.asyncio
async def test_update_user_strips_all_reserved_keys():
    """Every reserved key is stripped even when present together."""
    captured = {}
    with patch.object(auth_service, "update_user", side_effect=_fake_update(captured)):
        from app.api.auth import update_user

        admin = type("Admin", (), {"id": 1})()
        req = _Req({
            "email": "x@y.test",
            "full_name": "Ada",
            "roles": ["user"],
            "is_active": True,
            "mfa_enabled": False,
            "password": "pw",
            "keepme": 1,
        })
        await update_user(req, user_id=7, admin_user=admin, db=None)

    cd = captured["custom_data"]
    for key in ("email", "full_name", "roles", "is_active", "mfa_enabled", "password"):
        assert key not in cd
    assert cd.get("keepme") == 1


@pytest.mark.asyncio
async def test_update_user_empty_body_leaves_custom_data_none():
    """No JSON body => custom_data stays None (not overwritten)."""
    captured = {}
    with patch.object(auth_service, "update_user", side_effect=_fake_update(captured)):
        from app.api.auth import update_user

        admin = type("Admin", (), {"id": 1})()
        req = _Req(None)
        await update_user(req, user_id=7, admin_user=admin, db=None)

    assert "custom_data" not in captured

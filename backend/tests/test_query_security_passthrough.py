"""
Regression tests for findings #14 / #18: CMDB list/detail (`list_cis`/`get_ci`)
and form detail (`get_form`) call ``get_visible_fields`` / ``get_editable_fields``
on ``query_security_service``. Those methods lived only on
``role_permission_service``, so the calls raised AttributeError -> HTTP 500.

The fix adds delegating passthrough methods on ``QuerySecurityService``. These
tests pin that delegation: the passthroughs must forward to
``role_permission_service`` with the same args and return its result.
"""
import pytest

from app.services.query_security_service import query_security_service


@pytest.mark.asyncio
async def test_get_visible_fields_delegates_to_role_permission_service(monkeypatch):
    calls = {}

    async def fake(db, user, table_name):
        calls.update(db=db, user=user, table_name=table_name)
        return ["id", "username"]

    monkeypatch.setattr(
        "app.models.role_permissions.role_permission_service.get_visible_fields",
        fake,
    )

    class _User:
        roles = []

    db = object()
    result = await query_security_service.get_visible_fields(db, _User(), "users")

    assert result == ["id", "username"]
    # Forwarded with the exact args the caller supplied.
    assert calls["db"] is db
    assert calls["table_name"] == "users"


@pytest.mark.asyncio
async def test_get_editable_fields_delegates_to_role_permission_service(monkeypatch):
    async def fake(db, user, table_name):
        return ["*"]

    monkeypatch.setattr(
        "app.models.role_permissions.role_permission_service.get_editable_fields",
        fake,
    )

    class _User:
        roles = []

    result = await query_security_service.get_editable_fields(object(), _User(), "forms")
    assert result == ["*"]


@pytest.mark.asyncio
async def test_passthrough_methods_exist():
    """The methods must be callable on the instance (previously missing)."""
    assert hasattr(query_security_service, "get_visible_fields")
    assert hasattr(query_security_service, "get_editable_fields")

"""
Regression tests for findings #11: the visual-query endpoint must apply
field-level RBAC filtering. ``execute_visual_query`` returns its rows under the
``"items"`` key, but ``run_visual_query`` guarded on ``"results"`` — a key that
never exists — so ``filter_query_results`` was never called and every column
(including sensitive ones) leaked to the caller.

These tests assert the endpoint routes ``items`` through ``filter_query_results``
so restricted columns are stripped from the response.
"""
import pytest

from app.api import data_query
from app.services.query_security_service import query_security_service


SENSITIVE_ROWS = [
    {"id": 1, "username": "ada", "password_hash": "s3cret", "ldap_dn": "cn=ada"},
    {"id": 2, "username": "linus", "password_hash": "pw", "ldap_dn": "cn=linus"},
]


@pytest.fixture
async def _grant_access(monkeypatch):
    """Grant view access and make execute_visual_query return sensitive rows."""
    async def _yes(*a, **k):
        return True

    monkeypatch.setattr(query_security_service, "validate_query_access", _yes)

    async def fake_execute(db, table_name="", **kwargs):
        return {"items": [dict(r) for r in SENSITIVE_ROWS], "total": 2,
                "limit": 100, "offset": 0}

    monkeypatch.setattr(data_query, "execute_visual_query", fake_execute)

    class _User:
        id = 1
        role = "developer"
        roles = []

    return _User()


@pytest.mark.asyncio
async def test_visual_query_filters_sensitive_columns(monkeypatch, _grant_access):
    """Sensitive columns must be stripped from the response by filter_query_results."""

    async def fake_filter(db, user, table_name, results, action="view"):
        return [
            {k: v for k, v in row.items() if k not in ("password_hash", "ldap_dn")}
            for row in results
        ]

    monkeypatch.setattr(query_security_service, "filter_query_results", fake_filter)

    result = await data_query.run_visual_query(
        {"table": "users", "filters": []}, current_user=_grant_access, db=None
    )

    assert "items" in result
    for row in result["items"]:
        assert "password_hash" not in row
        assert "ldap_dn" not in row
    # Non-sensitive field survives.
    assert result["items"][0]["username"] == "ada"


@pytest.mark.asyncio
async def test_visual_query_applies_filter_to_items_key(monkeypatch, _grant_access):
    """The filter must be invoked on the 'items' key (the real return key).

    If the endpoint still guarded on the stale 'results' key, the unfiltered
    rows — with sensitive columns intact — would be returned. This pins that
    behavior to the correct key.
    """
    seen = {}

    async def fake_filter(db, user, table_name, results, action="view"):
        seen["rows"] = results
        return results

    monkeypatch.setattr(query_security_service, "filter_query_results", fake_filter)

    result = await data_query.run_visual_query(
        {"table": "users"}, current_user=_grant_access, db=None
    )

    # The exact list we returned under 'items' was passed to the filter...
    assert seen["rows"] is result["items"]
    # ...and the filtered output is what the caller receives.
    assert len(result["items"]) == 2

"""
G7: data-export cap/rate-limit alerting.

Alerts reuse the existing admin notification channels (email/Slack/webhook), are
best-effort, and dedupe repeated events. This module verifies:

  * cap events (clamped POST limit, cap-sized table export) emit one alert with
    redacted metadata while ordinary exports stay silent;
  * rate-limit events on export paths alert, while the shared limiter on other
    routers stays silent;
  * dedupe and dispatch failures cannot change the endpoint/rate-limit response.
"""
import types

import pytest
from fastapi import HTTPException

from app.api import data_export
from app.core.config import settings
from app.services import export_alert_service as alerts
from app.services.query_security_service import query_security_service
from app.services.rate_limiter import (
    api_rate_limiter,
    require_api_rate_limit,
    require_export_rate_limit,
)


@pytest.fixture(autouse=True)
def _isolated_alerts():
    """Fresh dedupe window and default settings for every test."""
    alerts.export_alert_cooldown.reset()
    api_rate_limiter.reset_all()
    saved = (
        settings.export_alerts_enabled,
        settings.api_requests_per_window,
        settings.api_request_window_seconds,
    )
    object.__setattr__(settings, "export_alerts_enabled", True)
    object.__setattr__(settings, "api_requests_per_window", 60)
    object.__setattr__(settings, "api_request_window_seconds", 60)
    yield
    object.__setattr__(settings, "export_alerts_enabled", saved[0])
    object.__setattr__(settings, "api_requests_per_window", saved[1])
    object.__setattr__(settings, "api_request_window_seconds", saved[2])
    alerts.export_alert_cooldown.reset()
    api_rate_limiter.reset_all()


class _User:
    id = 42


def _request(path="/data-export/query", host="198.51.100.7"):
    return types.SimpleNamespace(
        client=types.SimpleNamespace(host=host),
        url=types.SimpleNamespace(path=path),
    )


def _capture_cap(monkeypatch):
    captured = []

    async def fake_alert(**kwargs):
        captured.append(kwargs)
        return True

    monkeypatch.setattr(data_export, "alert_export_cap", fake_alert)
    return captured


async def _allow_access(monkeypatch):
    async def yes_access(db, user, table_name, action="view"):
        return True

    monkeypatch.setattr(query_security_service, "validate_query_access", yes_access)


# --------------------------------------------------------------------------- #
# Cap alerts in the export endpoints
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_query_export_alerts_when_limit_is_clamped(monkeypatch):
    captured = _capture_cap(monkeypatch)
    await _allow_access(monkeypatch)

    seen = {}

    async def fake_export(db, **kwargs):
        seen.update(kwargs)
        return "csv"

    monkeypatch.setattr(data_export, "export_query_to_csv", fake_export)

    response = await data_export.export_query(
        query_body={"table": "users", "limit": 250000},
        current_user=_User(),
        db=None,
    )

    assert response.media_type == "text/csv"
    assert seen["limit"] == alerts.EXPORT_ROW_CAP
    assert len(captured) == 1
    assert captured[0]["requested_limit"] == 250000
    assert captured[0]["applied_limit"] == alerts.EXPORT_ROW_CAP
    assert captured[0]["table"] == "users"
    assert captured[0]["user_id"] == 42
    assert captured[0]["path"] == "/data-export/query"


@pytest.mark.asyncio
async def test_query_export_below_cap_is_silent(monkeypatch):
    captured = _capture_cap(monkeypatch)
    await _allow_access(monkeypatch)

    async def fake_export(db, **kwargs):
        return "csv"

    monkeypatch.setattr(data_export, "export_query_to_csv", fake_export)

    await data_export.export_query(
        query_body={"table": "users", "limit": 1000},
        current_user=_User(),
        db=None,
    )
    assert captured == []


@pytest.mark.asyncio
async def test_table_export_alerts_at_row_cap(monkeypatch):
    captured = _capture_cap(monkeypatch)
    await _allow_access(monkeypatch)

    async def fake_export(db, table_name, columns, limit, current_user, stats):
        stats["row_count"] = alerts.EXPORT_ROW_CAP
        return "csv"

    monkeypatch.setattr(data_export, "export_table_to_csv", fake_export)

    await data_export.export_table(
        table_name="users", columns=None, limit=alerts.EXPORT_ROW_CAP,
        current_user=_User(), db=None,
    )
    assert len(captured) == 1
    assert captured[0]["row_count"] == alerts.EXPORT_ROW_CAP


@pytest.mark.asyncio
async def test_table_export_below_cap_is_silent(monkeypatch):
    captured = _capture_cap(monkeypatch)
    await _allow_access(monkeypatch)

    async def fake_export(db, table_name, columns, limit, current_user, stats):
        stats["row_count"] = 5
        return "csv"

    monkeypatch.setattr(data_export, "export_table_to_csv", fake_export)

    await data_export.export_table(
        table_name="users", columns=None, limit=100,
        current_user=_User(), db=None,
    )
    assert captured == []


@pytest.mark.asyncio
async def test_cap_alert_failure_does_not_break_export(monkeypatch):
    await _allow_access(monkeypatch)

    async def raising_alert(**kwargs):
        raise RuntimeError("notification channels down")

    monkeypatch.setattr(data_export, "alert_export_cap", raising_alert)

    async def fake_export(db, **kwargs):
        return "csv"

    monkeypatch.setattr(data_export, "export_query_to_csv", fake_export)

    response = await data_export.export_query(
        query_body={"table": "users", "limit": 150000},
        current_user=_User(),
        db=None,
    )
    assert response.status_code == 200
    assert response.body == b"csv"


# --------------------------------------------------------------------------- #
# The alert service itself
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_alert_dispatch_uses_export_type_and_redacted_context(monkeypatch):
    dispatched = []

    async def fake_notify_admins(**kwargs):
        dispatched.append(kwargs)

    monkeypatch.setattr(alerts, "notify_admins", fake_notify_admins)

    sent = await alerts.alert_export_cap(
        table="users", requested_limit=250000, applied_limit=100000,
        row_count=100000, user_id=9, client_ip="198.51.100.1",
        path="/data-export/query",
    )

    assert sent is True
    assert dispatched[0]["type"] == "export_cap_reached"
    context = dispatched[0]["context"]
    assert context["table"] == "users"
    assert context["requested_limit"] == 250000
    assert context["user_id"] == 9
    # No query payload/filter values ever reach the alert.
    assert "filters" not in context
    assert "query_body" not in context


@pytest.mark.asyncio
async def test_repeated_cap_alerts_are_deduped(monkeypatch):
    calls = []

    async def fake_notify_admins(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(alerts, "notify_admins", fake_notify_admins)

    kwargs = dict(table="users", user_id=9)
    assert await alerts.alert_export_cap(**kwargs) is True
    assert await alerts.alert_export_cap(**kwargs) is False
    assert len(calls) == 1

    # A different table is a distinct event.
    assert await alerts.alert_export_cap(table="tasks", user_id=9) is True
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_disabled_alerts_are_noop(monkeypatch):
    calls = []

    async def fake_notify_admins(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(alerts, "notify_admins", fake_notify_admins)
    object.__setattr__(settings, "export_alerts_enabled", False)

    assert await alerts.alert_export_cap(table="users") is False
    assert calls == []


# --------------------------------------------------------------------------- #
# Rate-limit alerts (only on export paths)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_export_rate_limit_alert_on_over_limit(monkeypatch):
    seen = []

    async def fake_alert(**kwargs):
        seen.append(kwargs)
        return True

    import app.services.export_alert_service as module
    monkeypatch.setattr(module, "alert_export_rate_limited", fake_alert)

    object.__setattr__(settings, "api_requests_per_window", 1)
    object.__setattr__(settings, "api_request_window_seconds", 60)

    await require_export_rate_limit(_request())
    with pytest.raises(HTTPException) as exc:
        await require_export_rate_limit(_request())

    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"] == "60"
    assert len(seen) == 1
    assert seen[0]["path"] == "/data-export/query"
    assert seen[0]["client_ip"] == "198.51.100.7"


@pytest.mark.asyncio
async def test_rate_limited_alert_failure_still_returns_429(monkeypatch):
    async def failing_alert(**kwargs):
        raise RuntimeError("channels down")

    import app.services.export_alert_service as module
    monkeypatch.setattr(module, "alert_export_rate_limited", failing_alert)

    object.__setattr__(settings, "api_requests_per_window", 1)
    await require_export_rate_limit(_request(path="/data-export/table/users"))
    with pytest.raises(HTTPException) as exc:
        await require_export_rate_limit(_request(path="/data-export/table/users"))
    assert exc.value.status_code == 429


def test_shared_rate_limit_dependency_does_not_alert(monkeypatch):
    seen = []

    async def fake_alert(**kwargs):
        seen.append(kwargs)

    import app.services.export_alert_service as module
    monkeypatch.setattr(module, "alert_export_rate_limited", fake_alert)

    object.__setattr__(settings, "api_requests_per_window", 1)
    require_api_rate_limit(_request(path="/ai/chat"))
    with pytest.raises(HTTPException):
        require_api_rate_limit(_request(path="/ai/chat"))
    assert seen == []

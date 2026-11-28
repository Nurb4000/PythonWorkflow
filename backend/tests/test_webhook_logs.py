"""Tests for M4: persistent webhook execution log + admin API.

Covers both halves of the feature:

* every outbound attempt is emitted by ``OutgoingWebhookSender`` with retry
  context, and ``log_webhook_event`` persists a redacted, size-capped row;
* the admin API lists/filters/summarises events, returns payload detail, scopes
  rows to the caller's tenant, and prunes only that tenant's expired rows.

No test hits the network; the sender uses an injected fake ``httpx.AsyncClient``.
All persistence uses the fresh-schema PostgreSQL ``db_engine`` fixture.
"""
import time
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api import webhook_logs as api
from app.models.auth import User
from app.models.schemas import Workflow  # noqa: F401 -- register schema models on metadata
from app.models.tenancy import Tenant
from app.models.webhook_log import WebhookLog
from app.services import webhook_log_service as logs_service
from app.services.outgoing_webhook import (
    OutgoingWebhookSender,
    WebhookAttempt,
    WebhookRequest,
)


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #
@pytest_asyncio.fixture
async def session(db_engine):
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest.fixture
def patch_log_session(monkeypatch, db_engine):
    """Point the log service's private sessions at the test database."""
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(logs_service, "async_session_factory", factory)
    # Suppress the hourly auto-prune so it cannot interfere with explicit cleanup tests.
    monkeypatch.setattr(logs_service, "_last_prune", time.monotonic())
    return factory


async def _make_tenant(session, tenant_id, slug):
    tenant = Tenant(id=tenant_id, name=f"Tenant {tenant_id}", slug=slug, is_active=True)
    session.add(tenant)
    await session.flush()
    return tenant


async def _make_admin(session, user_id, tenant_id):
    admin = User(
        id=user_id,
        username=f"admin{user_id}",
        email=f"admin{user_id}@test.local",
        password_hash="x",
        role="admin",
        tenant_id=tenant_id,
    )
    session.add(admin)
    await session.flush()
    return admin


async def _seed_log(
    session,
    *,
    tenant_id=1,
    event_type="webhook",
    status="success",
    success=True,
    status_code=200,
    attempt=1,
    will_retry=False,
    idempotency_key="",
    created_at=None,
):
    row = WebhookLog(
        direction="incoming" if event_type in ("webhook", "api_trigger") else "outgoing",
        event_type=event_type,
        status=status,
        success=success,
        tenant_id=tenant_id,
        endpoint="/webhook/1",
        status_code=status_code,
        attempt=attempt,
        max_attempts=2,
        will_retry=will_retry,
        idempotency_key=idempotency_key,
        detail="triggered",
    )
    session.add(row)
    if created_at is not None:
        row.created_at = created_at
    await session.flush()
    return row


# --------------------------------------------------------------------------- #
# Redaction helpers
# --------------------------------------------------------------------------- #
def test_redact_payload_masks_secrets_recursively():
    payload = {
        "order": {"id": 7, "api_key": "super-secret", "safe": "yes"},
        "Authorization": "Bearer abc",
        "x-api-token": "nope",
        "password": "hunter2",
        "X-Signature": "sha256=deadbeef",
    }
    clean = logs_service.redact_payload(payload)
    assert clean["order"]["api_key"] == "<redacted>"
    assert clean["order"]["safe"] == "yes"
    assert clean["Authorization"] == "<redacted>"
    assert clean["x-api-token"] == "<redacted>"
    assert clean["password"] == "<redacted>"
    assert clean["X-Signature"] == "<redacted>"


def test_redact_payload_caps_oversized_values():
    clean = logs_service.redact_payload({"blob": "x" * 10000}, max_chars=200)
    assert clean["_truncated"] is True
    assert len(clean["preview"]) == 200


def test_safe_endpoint_strips_query_and_masks_opaque_tokens():
    url = "https://hooks.example.com/services/T000/B000/abcdefghijklmnopqrstuvwxyz?token=secret"
    safe = logs_service.safe_endpoint(url)
    assert "token=secret" not in safe
    assert "abcdefghijklmnopqrstuvwxyz" not in safe
    assert safe.startswith("https://hooks.example.com/services/")
    assert logs_service.safe_endpoint("/webhook/42", incoming=True) == "/webhook/42"


# --------------------------------------------------------------------------- #
# Persistence + sender instrumentation
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_log_webhook_event_persists_redacted_row(session, patch_log_session):
    await _make_tenant(session, 1, "default")
    await session.commit()

    row_id = await logs_service.log_webhook_event(
        direction=logs_service.DIRECTION_OUTGOING,
        event_type=logs_service.EVENT_NOTIFICATION_WEBHOOK,
        endpoint="https://hooks.example.com/services/T1/B2/abcdefghijklmnopqrstuvwxyz?x=1",
        success=False,
        status=logs_service.STATUS_RETRY,
        tenant_id=1,
        idempotency_key="idem-1",
        attempt=2,
        max_attempts=3,
        will_retry=True,
        status_code=503,
        duration_ms=125,
        detail="HTTP 503: unavailable",
        request_payload={"text": "hello", "webhook_secret": "do-not-store"},
    )
    assert row_id is not None

    row = (await session.execute(select(WebhookLog).where(WebhookLog.id == row_id))).scalar_one()
    assert row.status == "retry"
    assert row.attempt == 2 and row.max_attempts == 3 and row.will_retry is True
    assert row.status_code == 503 and row.duration_ms == 125
    assert row.idempotency_key == "idem-1"
    assert "x=1" not in row.endpoint
    assert row.request_payload["webhook_secret"] == "<redacted>"


class FakeResponse:
    def __init__(self, status_code, text="ok"):
        self.status_code = status_code
        self.text = text


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, *, content=None, headers=None, timeout=None):
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_sender_emits_one_attempt_record_per_retry():
    attempts = []

    async def logger(attempt: WebhookAttempt) -> None:
        attempts.append(attempt)

    sender = OutgoingWebhookSender(
        client=FakeClient([FakeResponse(503, "busy"), FakeResponse(200)]),
        base_delay=0.0,
    )
    result = await sender.deliver(
        WebhookRequest(
            url="https://example.com/hook",
            payload={"hello": "world"},
            secret="s3cret",
            attempt_logger=logger,
            log_event_type="notification_webhook",
            log_context={"run_id": 9},
        )
    )

    assert result.success is True and result.attempt == 2
    assert len(attempts) == 2
    assert attempts[0].status_code == 503 and attempts[0].will_retry is True
    assert attempts[1].status_code == 200 and attempts[1].success is True
    assert attempts[0].idempotency_key == attempts[1].idempotency_key == result.idempotency_key
    assert attempts[0].attempt == 1 and attempts[1].attempt == 2
    assert attempts[0].event_type == "notification_webhook"
    assert attempts[0].context == {"run_id": 9}
    assert all(isinstance(a.duration_ms, int) for a in attempts)


# --------------------------------------------------------------------------- #
# Admin API
# --------------------------------------------------------------------------- #
def _list_args(**overrides):
    args = dict(
        direction=None,
        event_type=None,
        status=None,
        success=None,
        workflow_id=None,
        run_id=None,
        idempotency_key=None,
        q=None,
        since=None,
        until=None,
        page=1,
        page_size=50,
    )
    args.update(overrides)
    return args


@pytest.mark.asyncio
async def test_list_filters_and_scopes_to_active_tenant(session, patch_log_session):
    await _make_tenant(session, 1, "default")
    await _make_tenant(session, 2, "other")
    admin = await _make_admin(session, 1, 1)
    await _seed_log(session, tenant_id=1, status="success", idempotency_key="own-1")
    await _seed_log(session, tenant_id=1, status="failed", success=False, status_code=503)
    await _seed_log(session, tenant_id=2, status="success", idempotency_key="other-1")
    await _seed_log(session, tenant_id=None, status="success", idempotency_key="system-1")
    await session.commit()

    all_rows = await api.list_webhook_logs(db=session, current_user=admin, **_list_args())
    assert all_rows["total"] == 3  # tenant 1 + platform-level row
    assert {r["idempotency_key"] for r in all_rows["items"]} == {"own-1", "", "system-1"}

    failed = await api.list_webhook_logs(
        db=session, current_user=admin, **_list_args(status="failed")
    )
    assert failed["total"] == 1 and failed["items"][0]["status_code"] == 503

    searched = await api.list_webhook_logs(
        db=session, current_user=admin, **_list_args(q="other-1")
    )
    assert searched["total"] == 0  # belongs to another tenant, not visible


@pytest.mark.asyncio
async def test_stats_and_detail_with_payload(session, patch_log_session):
    await _make_tenant(session, 1, "default")
    await _make_admin(session, 1, 1)
    row = await _seed_log(session, tenant_id=1, idempotency_key="detail-key")
    await session.commit()  # tenant must be visible to the log service's own session
    row_id = await logs_service.log_webhook_event(
        direction="outgoing",
        event_type="notification_slack",
        endpoint="https://hooks.example.com/services/T1/B2/abcdefghijklmnopqrstuvwxyz",
        success=False,
        status="failed",
        tenant_id=1,
        status_code=500,
        duration_ms=80,
        will_retry=False,
    )
    assert row_id is not None
    await session.commit()

    stats = await api.webhook_log_stats(hours=24, db=session, current_user=await session.get(User, 1))
    assert stats["total"] == 2
    assert stats["incoming"] == 1 and stats["outgoing"] == 1
    assert stats["success"] == 1 and stats["failed"] == 1

    detail = await api.get_webhook_log(row.id, db=session, current_user=await session.get(User, 1))
    assert detail["idempotency_key"] == "detail-key"
    assert "request_payload" in detail
    listing = await api.list_webhook_logs(db=session, current_user=await session.get(User, 1), **_list_args())
    assert "request_payload" not in listing["items"][0]


@pytest.mark.asyncio
async def test_detail_rejects_other_tenant(session, patch_log_session):
    await _make_tenant(session, 1, "default")
    await _make_tenant(session, 2, "other")
    other_admin = await _make_admin(session, 2, 2)
    row = await _seed_log(session, tenant_id=1)
    await session.commit()

    with pytest.raises(HTTPException) as exc:
        await api.get_webhook_log(row.id, db=session, current_user=other_admin)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_cleanup_only_removes_visible_tenant_rows(session, patch_log_session):
    await _make_tenant(session, 1, "default")
    await _make_tenant(session, 2, "other")
    admin = await _make_admin(session, 1, 1)
    old = datetime.now(timezone.utc) - timedelta(days=10)
    own = await _seed_log(session, tenant_id=1, created_at=old)
    other = await _seed_log(session, tenant_id=2, created_at=old)
    system = await _seed_log(session, tenant_id=None, created_at=old)
    await session.commit()

    result = await api.cleanup_webhook_logs(
        older_than_days=1, db=session, current_user=admin
    )
    assert result["deleted"] == 1
    ids = {row.id for row in (await session.execute(select(WebhookLog))).scalars().all()}
    assert own.id not in ids
    assert other.id in ids
    assert system.id in ids

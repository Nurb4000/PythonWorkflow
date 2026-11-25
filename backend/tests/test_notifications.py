"""Regression tests for in-app notifications (Feature-Plan §2.3).

Covers three things:
- the notification service helper (create + unread count)
- the notification API endpoints (per-user scoping, read / read-all, delete, and
  the 403/404 authz paths)
- the event wiring: assigning a human_task to a user creates a notification for
  them (the bug this feature fixes -- previously no notification was created).

The endpoint-logic tests call the endpoint coroutines directly with a
``current_user`` and ``db`` (same convention as ``test_audit_authorization``
Part B); the wiring test drives the real engine's human-step handler. All use
the fresh-schema PostgreSQL ``db_engine`` fixture from tests/conftest.py.
"""
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api import notifications as notif_api
from app.models.auth import User
from app.models.schemas import Notification, Task, WorkflowRun
from app.schemas.workflow import WorkflowCreate
from app.services import workflow_engine as we_module
from app.services.notification_service import create_notification, unread_count
from app.services.workflow_engine import WorkflowEngine


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest_asyncio.fixture
async def db_session(db_engine):
    async with async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)() as s:
        yield s


@pytest_asyncio.fixture
async def session(db_engine):
    async with async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)() as s:
        yield s


@pytest.fixture
def engine(db_engine, monkeypatch):
    """WorkflowEngine whose background tasks use the test database."""
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(we_module, "async_session_factory", factory)
    return WorkflowEngine()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _make_user(s, uid):
    u = User(id=uid, username=f"user{uid}", email=f"user{uid}@test.local",
             password_hash="x", role="user")
    s.add(u)
    await s.flush()
    return u


async def _make_notification(db, user_id, title="t", message="m", type="task_assigned", is_read=False):
    n = Notification(user_id=user_id, title=title, message=message, type=type, is_read=is_read)
    db.add(n)
    await db.flush()
    return n


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_create_notification_flushes(db_session):
    u = await _make_user(db_session, 1)
    n = await create_notification(db_session, u.id, "Hi", "There", type="info")
    assert n.id is not None
    stored = (await db_session.execute(
        select(Notification).where(Notification.id == n.id)
    )).scalar_one()
    assert stored.title == "Hi"
    assert stored.message == "There"
    assert stored.is_read is False


@pytest.mark.asyncio
async def test_unread_count_only_counts_unread_for_owner(db_session):
    u1 = await _make_user(db_session, 1)
    u2 = await _make_user(db_session, 2)
    await _make_notification(db_session, u1.id, is_read=False)
    await _make_notification(db_session, u1.id, is_read=True)
    await _make_notification(db_session, u2.id, is_read=False)
    assert await unread_count(db_session, u1.id) == 1
    assert await unread_count(db_session, u2.id) == 1


# --------------------------------------------------------------------------- #
# Endpoint logic (called directly with current_user + db)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_list_scoped_to_current_user(db_session):
    u1 = await _make_user(db_session, 1)
    u2 = await _make_user(db_session, 2)
    await _make_notification(db_session, u1.id, title="A")
    await _make_notification(db_session, u1.id, title="B")
    await _make_notification(db_session, u2.id, title="C")
    resp = await notif_api.list_notifications(
        page=1, page_size=10, unread=False, type=None, db=db_session, current_user=u1
    )
    assert {n["title"] for n in resp["notifications"]} == {"A", "B"}
    assert resp["total"] == 2


@pytest.mark.asyncio
async def test_list_unread_filter(db_session):
    u1 = await _make_user(db_session, 1)
    await _make_notification(db_session, u1.id, is_read=False)
    await _make_notification(db_session, u1.id, is_read=True)
    resp = await notif_api.list_notifications(
        page=1, page_size=10, unread=True, type=None, db=db_session, current_user=u1
    )
    assert resp["total"] == 1
    assert all(n["is_read"] is False for n in resp["notifications"])


@pytest.mark.asyncio
async def test_list_type_filter(db_session):
    u1 = await _make_user(db_session, 1)
    await _make_notification(db_session, u1.id, type="task_assigned")
    await _make_notification(db_session, u1.id, type="sla_breach")
    resp = await notif_api.list_notifications(
        page=1, page_size=10, unread=False, type="task_assigned", db=db_session, current_user=u1
    )
    assert resp["total"] == 1
    assert resp["notifications"][0]["type"] == "task_assigned"


@pytest.mark.asyncio
async def test_unread_count_endpoint(db_session):
    u1 = await _make_user(db_session, 1)
    await _make_notification(db_session, u1.id, is_read=False)
    await _make_notification(db_session, u1.id, is_read=False)
    await _make_notification(db_session, u1.id, is_read=True)
    resp = await notif_api.unread_notification_count(db=db_session, current_user=u1)
    assert resp["unread"] == 2


@pytest.mark.asyncio
async def test_mark_read(db_session):
    u1 = await _make_user(db_session, 1)
    n = await _make_notification(db_session, u1.id, is_read=False)
    resp = await notif_api.mark_notification_read(
        notification_id=n.id, db=db_session, current_user=u1
    )
    assert resp["is_read"] is True
    refreshed = (await db_session.execute(
        select(Notification).where(Notification.id == n.id)
    )).scalar_one()
    assert refreshed.is_read is True


@pytest.mark.asyncio
async def test_mark_read_forbidden_for_other_user(db_session):
    u1 = await _make_user(db_session, 1)
    u2 = await _make_user(db_session, 2)
    n = await _make_notification(db_session, u1.id, is_read=False)
    with pytest.raises(HTTPException) as exc:
        await notif_api.mark_notification_read(
            notification_id=n.id, db=db_session, current_user=u2
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_mark_read_not_found(db_session):
    u1 = await _make_user(db_session, 1)
    with pytest.raises(HTTPException) as exc:
        await notif_api.mark_notification_read(
            notification_id=999999, db=db_session, current_user=u1
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_mark_all_read_scoped_to_user(db_session):
    u1 = await _make_user(db_session, 1)
    u2 = await _make_user(db_session, 2)
    await _make_notification(db_session, u1.id, is_read=False)
    await _make_notification(db_session, u1.id, is_read=False)
    await _make_notification(db_session, u2.id, is_read=False)
    resp = await notif_api.mark_all_read(db=db_session, current_user=u1)
    assert resp["marked_read"] == 2
    # A different user's unread notification is untouched.
    assert await unread_count(db_session, u2.id) == 1


@pytest.mark.asyncio
async def test_delete_notification(db_session):
    u1 = await _make_user(db_session, 1)
    n = await _make_notification(db_session, u1.id)
    resp = await notif_api.delete_notification(
        notification_id=n.id, db=db_session, current_user=u1
    )
    assert resp["deleted"] is True
    gone = (await db_session.execute(
        select(Notification).where(Notification.id == n.id)
    )).scalar_one_or_none()
    assert gone is None


@pytest.mark.asyncio
async def test_delete_forbidden_and_not_found(db_session):
    u1 = await _make_user(db_session, 1)
    u2 = await _make_user(db_session, 2)
    n = await _make_notification(db_session, u1.id)
    with pytest.raises(HTTPException) as exc:
        await notif_api.delete_notification(
            notification_id=n.id, db=db_session, current_user=u2
        )
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        await notif_api.delete_notification(
            notification_id=999999, db=db_session, current_user=u1
        )
    assert exc.value.status_code == 404


# --------------------------------------------------------------------------- #
# Event wiring: assigning a human_task creates a notification for the assignee
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_human_task_assignment_creates_notification(session, engine):
    user = await _make_user(session, 1)
    wf = await engine.create_workflow(
        session,
        WorkflowCreate(
            name="WF",
            steps=[
                {
                    "step_type": "human_task",
                    "definition": {"assigned_to_user_id": user.id, "title": "Approve"},
                }
            ],
            config={"start_step_ids": []},
        ),
    )
    await session.refresh(wf, attribute_names=["steps"])
    step = wf.steps[0]

    run = WorkflowRun(workflow_id=wf.id, status="running", input_data={})
    session.add(run)
    await session.flush()

    instance = SimpleNamespace(step_id=step.id, status="pending", output_data={}, completed_at=None)

    # Returning False means the workflow paused at the human step. Pass the real step
    # object (has id/title/definition); the handler reads step.id and step.definition.
    assert await engine._handle_human_step(session, run, instance, step) is False

    # A task was created for the assignee...
    task = (await session.execute(
        select(Task).where(Task.workflow_run_id == run.id)
    )).scalar_one()
    assert task.assigned_to_user_id == user.id

    # ...and a notification was created for them, tied to the task.
    notifs = (await session.execute(
        select(Notification).where(
            Notification.user_id == user.id, Notification.type == "task_assigned"
        )
    )).scalars().all()
    assert len(notifs) == 1
    assert notifs[0].related_entity_type == "task"
    assert notifs[0].related_entity_id == task.id
    assert notifs[0].is_read is False

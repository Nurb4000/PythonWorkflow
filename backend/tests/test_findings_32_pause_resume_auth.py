"""
Regression tests for findings #32 (pause_task/resume_task had no authorization).

Neither endpoint checked that the caller owns/is assigned to the task or their
group membership — any authenticated user could pause/resume *any* task by
iterating task_id (IDOR), and pausing removed tasks from SLA/OLA/date-target
breach detection.

Fix (findings #32): a shared `_task_paused_by` helper restricts pause/resume to
the assignee, a member of the task's assigned group, or an admin; others get 403.

Endpoints are called directly with a fake db + monkeypatched auth_service so no
live PostgreSQL is required.
"""
import pytest
from fastapi import HTTPException

from app.api.tasks import pause_task, resume_task
from app.services.auth_service import auth_service


class FakeGroup:
    def __init__(self, gid):
        self.id = gid


class FakeUser:
    def __init__(self, uid, role="user", roles=None, groups=None):
        self.id = uid
        self.role = role
        self.roles = roles
        self.groups = groups or []


class FakeTask:
    def __init__(self, tid, assigned_to_user_id=None, assigned_group_id=None):
        self.id = tid
        self.assigned_to_user_id = assigned_to_user_id
        self.assigned_group_id = assigned_group_id
        self.pause_state = None
        self.updated_at = None


class FakeResult:
    def __init__(self, task):
        self._task = task

    def scalar_one_or_none(self):
        return self._task


class FakeDB:
    def __init__(self, task):
        self._task = task
        self.committed = False

    async def execute(self, stmt):
        return FakeResult(self._task)

    async def commit(self):
        self.committed = True


def _fake_create_user(db=None, **kwargs):
    # Default: a plain user with no groups.
    return FakeUser(uid=kwargs.get("_uid", 10), role=kwargs.get("_role", "user"),
                    groups=kwargs.get("_groups"))


# --- assignee / admin / group member may pause & resume ------------------------

async def test_assignee_can_pause(monkeypatch):
    monkeypatch.setattr(auth_service, "create_user", _fake_create_user)
    db = FakeDB(FakeTask(1, assigned_to_user_id=10))
    res = await pause_task(task_id=1, pause_state="sla", current_user=FakeUser(10), db=db)
    assert res["pause_state"] == "sla"
    assert db.committed is True


async def test_admin_can_pause_any_task(monkeypatch):
    monkeypatch.setattr(auth_service, "create_user", _fake_create_user)
    db = FakeDB(FakeTask(7, assigned_to_user_id=99))  # owned by someone else
    res = await pause_task(task_id=7, pause_state="sla", current_user=FakeUser(1, role="admin"), db=db)
    assert res["task_id"] == 7
    assert db.committed is True


async def test_group_member_can_pause(monkeypatch):
    monkeypatch.setattr(auth_service, "create_user", _fake_create_user)
    db = FakeDB(FakeTask(3, assigned_group_id=42))
    res = await pause_task(task_id=3, pause_state="sla",
                           current_user=FakeUser(5, groups=[FakeGroup(42)]), db=db)
    assert res["task_id"] == 3
    assert db.committed is True


async def test_assignee_can_resume(monkeypatch):
    monkeypatch.setattr(auth_service, "create_user", _fake_create_user)
    db = FakeDB(FakeTask(1, assigned_to_user_id=10))
    res = await resume_task(task_id=1, current_user=FakeUser(10), db=db)
    assert res["message"] == "Task resumed"
    assert db.committed is True


# --- unauthorized callers are rejected with 403 -------------------------------

async def test_non_assignee_non_admin_gets_403(monkeypatch):
    monkeypatch.setattr(auth_service, "create_user", _fake_create_user)
    db = FakeDB(FakeTask(1, assigned_to_user_id=99))
    with pytest.raises(HTTPException) as exc:
        await pause_task(task_id=1, pause_state="sla", current_user=FakeUser(5), db=db)
    assert exc.value.status_code == 403
    assert db.committed is False


async def test_non_group_member_gets_403(monkeypatch):
    monkeypatch.setattr(auth_service, "create_user", _fake_create_user)
    db = FakeDB(FakeTask(3, assigned_group_id=42))
    with pytest.raises(HTTPException) as exc:
        await pause_task(task_id=3, pause_state="sla",
                         current_user=FakeUser(5, groups=[FakeGroup(99)]), db=db)
    assert exc.value.status_code == 403


async def test_resume_unauthorized_gets_403(monkeypatch):
    monkeypatch.setattr(auth_service, "create_user", _fake_create_user)
    db = FakeDB(FakeTask(1, assigned_to_user_id=99))
    with pytest.raises(HTTPException) as exc:
        await resume_task(task_id=1, current_user=FakeUser(5), db=db)
    assert exc.value.status_code == 403


# --- not found still 404 ------------------------------------------------------

async def test_missing_task_gets_404(monkeypatch):
    monkeypatch.setattr(auth_service, "create_user", _fake_create_user)

    class EmptyDB(FakeDB):
        async def execute(self, stmt):
            class R:
                def scalar_one_or_none(r):
                    return None
            return R()

    class EmptyDB:
        async def execute(self, stmt):
            class R:
                def scalar_one_or_none(r):
                    return None
            return R()

    with pytest.raises(HTTPException) as exc:
        await pause_task(task_id=42, pause_state="sla", current_user=FakeUser(1, role="admin"), db=EmptyDB())
    assert exc.value.status_code == 404

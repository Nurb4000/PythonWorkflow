"""
Regression test for findings #21 (portal run_workflow gate skipped for non-user/staff).

The access gate at `run_workflow` only ran when `current_user.role in ["user",
"staff"]`. For admin / developer / cmdb_manager the published / portal_visible /
environment / group check was skipped entirely, so any of these roles could trigger
*any active workflow* through the portal — including unpublished, non-portal-visible,
or environment-restricted workflows.

Fix: apply the gate to ALL roles.

Asserts that an admin with an unpublished workflow is now rejected (403) and that a
valid production run still succeeds (proving the gate did not over-restrict).
"""
import pytest
from fastapi import HTTPException

from app.api import portal as portal_mod
from app.services.workflow_engine import WorkflowEngine


class FakeWorkflow:
    def __init__(self, wf_id=1, is_active=True, is_published=True, portal_visible=True, environment="production"):
        self.id = wf_id
        self.is_active = is_active
        self.is_published = is_published
        self.portal_visible = portal_visible
        self.environment = environment
        self.service_id = 1


class _Result:
    def __init__(self, obj=None, row=None):
        self._obj = obj
        self._row = row

    def scalar_one_or_none(self):
        return self._obj

    def fetchone(self):
        return self._row


class FakeDB:
    """First execute returns the workflow; any later execute returns the perm row."""
    def __init__(self, workflow, perm_row=None):
        self._n = 0
        self._workflow = workflow
        self._perm_row = perm_row

    async def execute(self, stmt):
        self._n += 1
        return _Result(obj=self._workflow if self._n == 1 else None, row=self._perm_row)


class _User:
    def __init__(self, role, uid=5, groups=None):
        self.role = role
        self.id = uid
        self.groups = groups or []


class _Run:
    def __init__(self):
        self.id = 999


@pytest.fixture()
def track_trigger(monkeypatch):
    state = {"called": False}

    async def fake_trigger(self, db, workflow_id, run_data):
        state["called"] = True
        return _Run()

    monkeypatch.setattr(WorkflowEngine, "trigger_workflow", fake_trigger)
    return state


async def _run(uid, role, workflow, db, track):
    try:
        await portal_mod.run_workflow(
            workflow_id=workflow.id,
            input_data={},
            current_user=_User(role, uid),
            db=db,
        )
        return ("ok", None)
    except HTTPException as e:
        return ("http", e)


@pytest.mark.asyncio
async def test_admin_unpublished_workflow_is_rejected(track_trigger):
    wf = FakeWorkflow(is_published=False, portal_visible=True, environment="production")
    db = FakeDB(wf)
    kind, err = await _run(5, "admin", wf, db, track_trigger)
    assert kind == "http"
    assert err.status_code == 403
    assert track_trigger["called"] is False  # gate blocked it before triggering


@pytest.mark.asyncio
async def test_admin_non_portal_visible_workflow_is_rejected(track_trigger):
    wf = FakeWorkflow(is_published=True, portal_visible=False, environment="production")
    db = FakeDB(wf)
    kind, err = await _run(5, "developer", wf, db, track_trigger)
    assert kind == "http"
    assert err.status_code == 403
    assert track_trigger["called"] is False


@pytest.mark.asyncio
async def test_admin_non_production_without_groups_is_rejected(track_trigger):
    wf = FakeWorkflow(is_published=True, portal_visible=True, environment="staging")
    db = FakeDB(wf, perm_row=None)  # no group permission row
    kind, err = await _run(5, "cmdb_manager", wf, db, track_trigger)
    assert kind == "http"
    assert err.status_code == 403
    assert track_trigger["called"] is False


@pytest.mark.asyncio
async def test_valid_production_run_succeeds_for_any_role(track_trigger):
    wf = FakeWorkflow(is_published=True, portal_visible=True, environment="production")
    db = FakeDB(wf)
    kind, err = await _run(5, "admin", wf, db, track_trigger)
    assert kind == "ok"
    assert err is None
    assert track_trigger["called"] is True

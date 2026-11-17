"""Regression tests for workflow version snapshots (Feature-Plan §2.4).

Covers the service + engine wiring and the three API endpoints:
- create captures a v1 snapshot; update captures a new, labelled snapshot;
- versions are listed newest-first and inspectable in full;
- restore reverts to an earlier snapshot and captures the result as a new version;
- endpoints 404 correctly for missing workflows/versions.

Run against local Postgres (db_engine fixture from tests/conftest.py).
"""
import pytest
import pytest_asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.auth import User
from app.models.schemas import Workflow, WorkflowVersion
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate
from app.services import workflow_engine as we_module
from app.services.workflow_engine import WorkflowEngine
import app.api.workflows as wf_api


@pytest_asyncio.fixture
async def session(db_engine):
    async with async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)() as s:
        yield s


@pytest.fixture
def engine(db_engine, monkeypatch):
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(we_module, "async_session_factory", factory)
    return WorkflowEngine()


async def _make_user(s, uid):
    u = User(id=uid, username=f"user{uid}", email=f"user{uid}@test.local",
             password_hash="x", role="developer")
    s.add(u)
    await s.flush()
    return u


def _steps(*types):
    return [{"step_type": t, "definition": {"url": f"http://x/{t}"}, "title": t} for t in types]


async def _count_versions(session, workflow_id):
    rows = (await session.execute(
        select(WorkflowVersion).where(WorkflowVersion.workflow_id == workflow_id)
    )).scalars().all()
    return rows


# --------------------------------------------------------------------------- #
# Engine / service wiring
# --------------------------------------------------------------------------- #
async def test_create_captures_version_1_snapshot(session, engine):
    wf = await engine.create_workflow(
        session, WorkflowCreate(name="V", steps=_steps("delay", "api_call")),
    )
    versions = await _count_versions(session, wf.id)
    assert len(versions) == 1
    v = versions[0]
    assert v.version_number == 1
    assert len(v.snapshot["steps"]) == 2
    assert [s["step_type"] for s in v.snapshot["steps"]] == ["delay", "api_call"]
    # connections live inside each step's definition JSON
    assert v.snapshot["steps"][0]["definition"]["url"] == "http://x/delay"


async def test_update_captures_new_labelled_version(session, engine):
    wf = await engine.create_workflow(
        session, WorkflowCreate(name="V", steps=_steps("delay")),
    )
    await engine.update_workflow(
        session, wf.id,
        WorkflowUpdate(steps=_steps("delay", "email"), version_label="ship it"),
    )
    wf = await session.get(Workflow, wf.id)
    assert wf.version == 2
    versions = sorted(await _count_versions(session, wf.id), key=lambda r: r.version_number)
    assert [r.version_number for r in versions] == [1, 2]
    # new snapshot carries the label and the updated graph; old one preserved
    v2 = versions[1]
    assert v2.label == "ship it"
    assert [s["step_type"] for s in v2.snapshot["steps"]] == ["delay", "email"]
    assert versions[0].version_number == 1 and len(versions[0].snapshot["steps"]) == 1


async def test_list_versions_newest_first(session, engine):
    wf = await engine.create_workflow(
        session, WorkflowCreate(name="V", steps=_steps("delay")),
    )
    await engine.update_workflow(session, wf.id, WorkflowUpdate(version_label="a"))
    await engine.update_workflow(session, wf.id, WorkflowUpdate(version_label="b"))
    listed = await wf_api.list_versions(session, wf.id)
    assert [v["version_number"] for v in listed] == [3, 2, 1]
    assert listed[0]["label"] == "b"
    assert all("step_count" in v for v in listed)


async def test_restore_creates_new_version_with_prior_content(session, engine):
    wf = await engine.create_workflow(
        session, WorkflowCreate(name="Orig", steps=_steps("a", "b")),
    )
    await engine.update_workflow(
        session, wf.id, WorkflowUpdate(steps=_steps("a", "c"), version_label="drift"),
    )
    wf = await session.get(Workflow, wf.id)
    v1_id = (await session.execute(
        select(WorkflowVersion.id).where(
            WorkflowVersion.workflow_id == wf.id,
            WorkflowVersion.version_number == 1,
        )
    )).scalar_one()

    restored = await wf_api.restore_version(session, wf.id, v1_id, created_by=None)
    assert restored is not None
    assert restored.version == 3
    # steps reloaded by restore_version reflect the reverted graph (a, b), not drifted (a, c)
    assert [s.step_type for s in restored.steps] == ["a", "b"]
    # verify via a fresh snapshot row for v3
    v3 = (await session.execute(
        select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == wf.id, WorkflowVersion.version_number == 3,
        )
    )).scalar_one()
    assert [s["step_type"] for s in v3.snapshot["steps"]] == ["a", "b"]
    assert v3.label == f"Restored from v1"
    # full history preserved: v1, v2, v3
    assert sorted(r.version_number for r in await _count_versions(session, wf.id)) == [1, 2, 3]


# --------------------------------------------------------------------------- #
# API endpoints
# --------------------------------------------------------------------------- #
async def test_list_versions_endpoint(session, engine):
    user = await _make_user(session, 7)
    wf = await engine.create_workflow(
        session, WorkflowCreate(name="V", steps=_steps("delay")),
    )
    resp = await wf_api.list_workflow_versions(wf.id, developer=user, db=session)
    assert isinstance(resp, list) and len(resp) == 1 and resp[0]["version_number"] == 1


async def test_list_versions_missing_workflow_404(session, engine):
    user = await _make_user(session, 8)
    with pytest.raises(Exception) as exc:
        await wf_api.list_workflow_versions(999999, developer=user, db=session)
    assert exc.value.status_code == 404


async def test_get_version_endpoint_and_404(session, engine):
    user = await _make_user(session, 9)
    wf = await engine.create_workflow(
        session, WorkflowCreate(name="V", steps=_steps("delay", "email")),
    )
    row = (await session.execute(
        select(WorkflowVersion).where(WorkflowVersion.workflow_id == wf.id)
    )).scalar_one()
    resp = await wf_api.get_workflow_version(wf.id, row.id, developer=user, db=session)
    assert resp["version_number"] == 1
    assert [s["step_type"] for s in resp["snapshot"]["steps"]] == ["delay", "email"]

    with pytest.raises(Exception) as exc:
        await wf_api.get_workflow_version(wf.id, 424242, developer=user, db=session)
    assert exc.value.status_code == 404


async def test_restore_endpoint_404_for_missing_version(session, engine):
    user = await _make_user(session, 10)
    wf = await engine.create_workflow(
        session, WorkflowCreate(name="V", steps=_steps("delay")),
    )
    import fastapi
    with pytest.raises(fastapi.HTTPException) as exc:
        await wf_api.restore_workflow_version(
            wf.id, 424242, request=None, developer=user, db=session,
        )
    assert exc.value.status_code == 404

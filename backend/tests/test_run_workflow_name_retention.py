"""Tests for snapshotting the workflow name on runs and retaining runs
when a workflow is deleted, so history stays identifiable."""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.schemas import Workflow, WorkflowRun
from app.services.workflow_engine import WorkflowEngine
from app.schemas.workflow import WorkflowCreate, WorkflowRunCreate


@pytest.fixture
async def db_session(db_engine):
    async_session = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


@pytest.mark.asyncio
async def test_run_snapshots_workflow_name_and_survives_deletion(db_session, monkeypatch):
    from app.services import workflow_engine as we

    # Do not actually execute the workflow in the background.
    async def _noop_execute(self, run_id):
        return None
    monkeypatch.setattr(we.WorkflowEngine, "_execute_workflow", _noop_execute)

    engine = WorkflowEngine()
    wf = await engine.create_workflow(db_session, WorkflowCreate(name="Snapshot WF"))
    assert wf.name == "Snapshot WF"

    run = await engine.trigger_workflow(
        db_session, wf.id, WorkflowRunCreate(input_data={"x": 1})
    )
    assert run.workflow_name == "Snapshot WF"

    # Reload the run fresh from the DB to confirm the snapshot persisted.
    fresh = (
        await db_session.execute(select(WorkflowRun).where(WorkflowRun.id == run.id))
    ).scalar_one()
    assert fresh.workflow_name == "Snapshot WF"

    # Delete the workflow; the run must be retained with the name.
    wf_row = (
        await db_session.execute(select(Workflow).where(Workflow.id == wf.id))
    ).scalar_one()
    await db_session.delete(wf_row)
    await db_session.commit()

    runs = (await db_session.execute(select(WorkflowRun))).scalars().all()
    assert len(runs) == 1
    assert runs[0].workflow_name == "Snapshot WF"
    assert runs[0].workflow_id is None


@pytest.mark.asyncio
async def test_run_without_workflow_keeps_snapshot_name(db_session):
    run = WorkflowRun(
        workflow_id=None,
        status="completed",
        triggered_by="manual",
        workflow_name="Deleted workflow name",
        input_data={},
        output_data={},
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    assert run.workflow_name == "Deleted workflow name"
    assert run.workflow_id is None

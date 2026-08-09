"""
Tests for the run-inspector backend support (plan S1-S3):

S1 - step metadata snapshotted onto step instances at trigger time
S2 - route_taken recorded on instances (graph + linear + condition)
S3 - StepInstanceResponse enriched (position, step_type, title,
     description, route_taken, custom_data, duration_seconds)
"""
import asyncio
import time

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.schemas import Workflow, WorkflowRun, StepInstance
from app.schemas.workflow import StepInstanceResponse, WorkflowCreate, WorkflowRunCreate
from app.services import workflow_engine as we_module
from app.services.workflow_engine import WorkflowEngine


# ---------------------------------------------------------------------------
# Fixtures: shared in-memory SQLite (StaticPool) so background engine sessions
# created via the patched async_session_factory see the same database.
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session(db_engine):
    async with async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)() as s:
        yield s


@pytest.fixture
def engine(db_engine, monkeypatch):
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(we_module, "async_session_factory", factory)
    return WorkflowEngine()


async def create_workflow(engine, session, steps, config=None):
    wf = await engine.create_workflow(session, WorkflowCreate(name="Inspector WF", steps=steps, config=config or {}))
    wf = await session.get(Workflow, wf.id)
    await session.refresh(wf, attribute_names=["steps"])
    return wf


async def wait_run(session, run_id, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        await asyncio.sleep(0.05)
        run = await session.get(WorkflowRun, run_id)
        if run is not None:
            await session.refresh(run)
            if run.status in ("completed", "failed", "waiting"):
                return run
    raise AssertionError("run did not finish in time")


async def instances_for(session, run_id):
    result = await session.execute(
        select(StepInstance).where(StepInstance.workflow_run_id == run_id)
    )
    return result.scalars().all()


# ---------------------------------------------------------------------------
# S1: snapshot population
# ---------------------------------------------------------------------------
class TestStepSnapshot:
    @pytest.mark.asyncio
    async def test_trigger_snapshots_step_metadata(self, engine, session):
        wf = await create_workflow(
            engine, session,
            [
                {"step_type": "delay", "definition": {"seconds": 0}},
                {"step_type": "delay", "definition": {"seconds": 0}},
            ],
        )
        await session.refresh(wf, attribute_names=["steps"])
        first, second = sorted(wf.steps, key=lambda s: s.position)
        first.title = "Fetch User"
        first.description = "Fetches the user record."
        first.definition = {**first.definition, "url": "https://example.com/user"}
        second.title = "Notify"
        second.definition = {**second.definition, "channel": "email"}
        await session.commit()

        run = await engine.trigger_workflow(session, wf.id, WorkflowRunCreate())
        run = await wait_run(session, run.id)
        assert run.status == "completed"

        instances = await instances_for(session, run.id)
        by_step = {i.step_id: i for i in instances}
        first_inst = by_step[first.id]
        assert first_inst.step_title == "Fetch User"
        assert first_inst.step_type == "delay"
        assert first_inst.step_description == "Fetches the user record."
        assert first_inst.step_definition.get("url") == "https://example.com/user"
        assert second.title == "Notify"
        assert by_step[second.id].step_definition.get("channel") == "email"


# ---------------------------------------------------------------------------
# S2: route_taken
# ---------------------------------------------------------------------------
class TestRouteTaken:
    @pytest.mark.asyncio
    async def test_graph_route_taken(self, engine, session):
        wf = await create_workflow(
            engine, session,
            [
                {"step_type": "delay", "definition": {"seconds": 0}},  # A
                {"step_type": "delay", "definition": {"seconds": 0}},  # B
                {"step_type": "delay", "definition": {"seconds": 0}},  # C
            ],
        )
        await session.refresh(wf, attribute_names=["steps"])
        a, b, c = sorted(wf.steps, key=lambda s: s.position)
        a.definition = {**a.definition, "next_step_ids": [b.id]}
        b.definition = {**b.definition, "next_step_ids": [c.id]}
        wf.config = {"start_step_ids": [a.id]}
        await session.commit()

        run = await engine.trigger_workflow(session, wf.id, WorkflowRunCreate())
        run = await wait_run(session, run.id)
        assert run.status == "completed"
        await asyncio.sleep(0.2)

        instances = await instances_for(session, run.id)
        by_step = {i.step_id: i for i in instances}
        assert by_step[a.id].route_taken == [b.id]
        assert by_step[b.id].route_taken == [c.id]
        assert by_step[c.id].route_taken == []

    @pytest.mark.asyncio
    async def test_condition_route_taken(self, engine, session):
        wf = await create_workflow(
            engine, session,
            [
                {"step_type": "condition", "definition": {"routes": []}},
                {"step_type": "delay", "definition": {"seconds": 0}},  # yes
                {"step_type": "delay", "definition": {"seconds": 0}},  # no
            ],
        )
        await session.refresh(wf, attribute_names=["steps"])
        cond, yes, no = sorted(wf.steps, key=lambda s: s.position)
        cond.definition = {
            "routes": [
                {"expression": "data['value'] > 5", "target_step_id": yes.id},
            ],
            "default_target_step_id": no.id,
        }
        wf.config = {"start_step_ids": [cond.id]}
        await session.commit()

        run = await engine.trigger_workflow(
            session, wf.id, WorkflowRunCreate(input_data={"value": 10})
        )
        run = await wait_run(session, run.id)
        assert run.status == "completed"
        await asyncio.sleep(0.2)

        instances = await instances_for(session, run.id)
        by_step = {i.step_id: i for i in instances}
        assert by_step[cond.id].route_taken == [yes.id]
        assert by_step[yes.id].status == "completed"
        assert by_step[no.id].status == "skipped"

    @pytest.mark.asyncio
    async def test_linear_route_taken(self, engine, session):
        # No explicit connections -> legacy linear execution.
        wf = await create_workflow(
            engine, session,
            [
                {"step_type": "delay", "definition": {"seconds": 0}},
                {"step_type": "delay", "definition": {"seconds": 0}},
            ],
        )
        await session.refresh(wf, attribute_names=["steps"])
        first, second = sorted(wf.steps, key=lambda s: s.position)
        await session.commit()

        run = await engine.trigger_workflow(session, wf.id, WorkflowRunCreate())
        run = await wait_run(session, run.id)
        assert run.status == "completed"
        await asyncio.sleep(0.2)

        instances = await instances_for(session, run.id)
        by_step = {i.step_id: i for i in instances}
        assert by_step[first.id].route_taken == [second.id]
        assert by_step[second.id].route_taken == []


# ---------------------------------------------------------------------------
# S3: response shape
# ---------------------------------------------------------------------------
class TestStepInstanceResponse:
    @pytest.mark.asyncio
    async def test_response_includes_enriched_fields(self, db_engine, session):
        from datetime import datetime, timedelta

        wf = Workflow(name="WF")
        session.add(wf)
        await session.flush()
        run = WorkflowRun(workflow_id=wf.id, status="failed", input_data={}, triggered_by="manual")
        session.add(run)
        await session.flush()
        inst = StepInstance(
            workflow_run_id=run.id,
            step_id=None,  # step was deleted -> snapshot must carry the info
            step_title="Legacy Step",
            step_type="api_call",
            step_description="Old step description",
            step_definition={"url": "https://example.com"},
            status="failed",
            input_data={"a": 1},
            output_data={},
            error_message="boom",
            position=2,
            started_at=datetime.utcnow() - timedelta(seconds=3),
            completed_at=datetime.utcnow(),
            custom_data={"route_taken": [7, 8]},
        )
        session.add(inst)
        await session.commit()
        await session.refresh(inst)

        resp = StepInstanceResponse.model_validate(inst)
        assert resp.step_id is None
        assert resp.position == 2
        assert resp.step_type == "api_call"
        assert resp.title == "Legacy Step"
        assert resp.description == "Old step description"
        assert resp.route_taken == [7, 8]
        assert resp.custom_data["route_taken"] == [7, 8]
        assert resp.error_message == "boom"
        assert resp.duration_seconds is not None and resp.duration_seconds > 2.9

    @pytest.mark.asyncio
    async def test_title_falls_back_to_step_type(self, db_engine, session):
        wf = Workflow(name="WF")
        session.add(wf)
        await session.flush()
        run = WorkflowRun(workflow_id=wf.id, status="pending", input_data={}, triggered_by="manual")
        session.add(run)
        await session.flush()
        inst = StepInstance(
            workflow_run_id=run.id,
            step_type="delay",
            step_title="",
            status="pending",
            input_data={},
            output_data={},
            position=0,
        )
        session.add(inst)
        await session.commit()

        resp = StepInstanceResponse.model_validate(inst)
        assert resp.title == "delay"

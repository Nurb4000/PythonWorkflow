"""
Tests for the date-target list API filters (INCIDENT_CHANGE_PLAN Phase 0.3/4.2):

- run_ids batch filter (comma-separated workflow run IDs) used by the
  task-dashboard date badges to decorate many runs in one request
- soft-deleted (is_active=False) targets are excluded from listings
- malformed run_ids is rejected with 400

The API functions are called directly (suite convention: no HTTP layer),
with a stub principal since these endpoints only require authentication.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.date_targets import list_date_targets, create_date_target
from app.models.date_targets import DateTarget
from app.models.schemas import WorkflowRun


@pytest_asyncio.fixture
async def session(db_engine):
    async with async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)() as s:
        yield s


@pytest.fixture
def user():
    return SimpleNamespace(id=1, role="admin", username="tester")


async def _add_run(session) -> WorkflowRun:
    run = WorkflowRun(status="completed", triggered_by="manual")
    session.add(run)
    await session.flush()
    return run


class TestListDateTargets:
    @pytest.mark.asyncio
    async def test_run_ids_batch_filter(self, session, user):
        run_a = await _add_run(session)
        run_b = await _add_run(session)
        run_c = await _add_run(session)
        soon = datetime.now(timezone.utc) + timedelta(days=1)
        for run in (run_a, run_b, run_c):
            session.add(
                DateTarget(
                    workflow_run_id=run.id,
                    target_key="change_target_completion",
                    target_datetime=soon,
                    status="pending",
                )
            )
        await session.commit()

        result = await list_date_targets(
            run_id=None,
            run_ids=f"{run_a.id},{run_c.id}",
            status=None,
            target_key=None,
            db=session,
            current_user=user,
        )

        assert sorted(t["workflow_run_id"] for t in result) == sorted([run_a.id, run_c.id])

    @pytest.mark.asyncio
    async def test_soft_deleted_excluded(self, session, user):
        run = await _add_run(session)
        session.add(
            DateTarget(
                workflow_run_id=run.id,
                target_key="k",
                target_datetime=datetime.now(timezone.utc) + timedelta(days=2),
                status="pending",
            )
        )
        deleted = DateTarget(
            workflow_run_id=run.id,
            target_key="gone",
            target_datetime=datetime.now(timezone.utc) + timedelta(days=3),
            status="pending",
            is_active=False,
        )
        session.add(deleted)
        await session.commit()

        result = await list_date_targets(
            run_id=None, run_ids=None, status=None, target_key=None, db=session, current_user=user
        )

        assert [t["target_key"] for t in result] == ["k"]

    @pytest.mark.asyncio
    async def test_malformed_run_ids_rejected(self, session, user):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await list_date_targets(
                run_id=None,
                run_ids="1,two,3",
                status=None,
                target_key=None,
                db=session,
                current_user=user,
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_create_then_list_roundtrip(self, session, user):
        run = await _add_run(session)
        await session.commit()
        due = datetime.now(timezone.utc) + timedelta(days=5)

        created = await create_date_target(
            {
                "workflow_run_id": run.id,
                "target_key": "change_target_completion",
                "target_datetime": due.isoformat(),
            },
            db=session,
            current_user=user,
        )
        assert created["status"] == "pending"
        assert created["target_key"] == "change_target_completion"

        stored = (
            await session.execute(DateTarget.__table__.select().where(DateTarget.id == created["id"]))
        ).mappings().one()
        assert stored["workflow_run_id"] == run.id


class TestCalculationStepStamping:
    @pytest.mark.asyncio
    async def test_executor_stamps_step_id(self, session):
        """Phase 4.3: calc-step targets carry the originating workflow_steps.id."""
        from app.models.schemas import Workflow, WorkflowStep
        from app.services.step_executors import CalculationExecutor

        wf = Workflow(name="Target WF")
        session.add(wf)
        await session.flush()
        step = WorkflowStep(workflow_id=wf.id, step_type="calculation", definition={}, position=0)
        session.add(step)
        run = WorkflowRun(status="running", triggered_by="manual")
        session.add(run)
        await session.flush()

        due = datetime.now(timezone.utc) + timedelta(days=3)
        output = await CalculationExecutor().execute(
            {
                "target_end_date": due.isoformat(),
                "_workflow_run_id": run.id,
                "_workflow_step_id": step.id,
            },
            {"expression": "data['target_end_date']", "date_target_key": "change_target_completion"},
            db=session,
        )

        assert output["date_target_created"] > 0
        target = await session.get(DateTarget, output["date_target_created"])
        assert target is not None
        assert target.workflow_run_id == run.id
        assert target.step_id == step.id

    @pytest.mark.asyncio
    async def test_executor_without_step_ref_stays_run_level(self, session):
        from app.services.step_executors import CalculationExecutor

        run = await _add_run(session)
        await session.commit()

        due = datetime.now(timezone.utc) + timedelta(days=1)
        output = await CalculationExecutor().execute(
            {"target_end_date": due.isoformat(), "_workflow_run_id": run.id},
            {"expression": "data['target_end_date']", "date_target_key": "k"},
            db=session,
        )

        target = await session.get(DateTarget, output["date_target_created"])
        assert target.step_id is None

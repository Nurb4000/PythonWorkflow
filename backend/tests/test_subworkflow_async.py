"""
G8: async (fire-and-forget) sub-workflow invocation.

The default ``sync`` behavior must remain untouched: it waits for the child and
merges ``result_data``. ``execution_mode: "async"`` returns as soon as the child
run has been created, exposing the child run id for downstream steps without
waiting for (or propagating) the child's outcome.
"""
import pytest

from app.models.schemas import Workflow, WorkflowRun
from app.services.step_executors import SubWorkflowExecutor


@pytest.fixture
async def db_session(db_engine):
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker

    async_session = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


async def _seed_child(db, name="sub-async"):
    wf = Workflow(name=name)
    db.add(wf)
    await db.flush()
    child = WorkflowRun(workflow_id=wf.id, status="pending")
    db.add(child)
    await db.flush()
    return wf, child


@pytest.mark.asyncio
async def test_async_mode_returns_launch_payload_without_waiting(db_session, monkeypatch):
    from app.services import workflow_engine as we_module

    wf, child = await _seed_child(db_session)
    captured = {}

    async def fake_trigger(db, workflow_id, run_data):
        captured["workflow_id"] = workflow_id
        captured["run_data"] = run_data
        return child

    async def must_not_wait(*args, **kwargs):
        raise AssertionError("async mode must not poll the child run")

    monkeypatch.setattr(we_module.workflow_engine, "trigger_workflow", fake_trigger)
    executor = SubWorkflowExecutor()
    monkeypatch.setattr(executor, "_wait_for_run_completion", must_not_wait)

    result = await executor.execute(
        input_data={
            "_workflow_run_id": 9,
            "_workflow_step_id": 4,
            "user_id": "abc",
        },
        step_definition={
            "workflow_id": wf.id,
            "execution_mode": "async",
            "input_data": {"user_id": "$input.user_id"},
            "timeout_seconds": 1,
        },
        db=db_session,
    )

    assert result["success"] is True
    assert result["execution_mode"] == "async"
    assert result["run_id"] == child.id
    assert result["status"] == "pending"
    assert result["result_data"] == {}
    assert result["duration_seconds"] is None

    assert captured["workflow_id"] == wf.id
    assert captured["run_data"].triggered_by == "sub_workflow"
    assert captured["run_data"].input_data == {"user_id": "abc"}


@pytest.mark.asyncio
async def test_async_mode_records_parent_lineage(db_session, monkeypatch):
    from app.services import workflow_engine as we_module

    wf, child = await _seed_child(db_session)

    async def fake_trigger(db, workflow_id, run_data):
        return child

    monkeypatch.setattr(we_module.workflow_engine, "trigger_workflow", fake_trigger)
    executor = SubWorkflowExecutor()

    await executor.execute(
        input_data={"_workflow_run_id": 11, "_workflow_step_id": 3},
        step_definition={
            "workflow_id": wf.id,
            "execution_mode": "async",
            "input_data": {},
        },
        db=db_session,
    )

    await db_session.refresh(child)
    assert child.custom_data["parent_run_id"] == 11
    assert child.custom_data["parent_step_id"] == 3
    assert child.custom_data["execution_mode"] == "async"


@pytest.mark.asyncio
async def test_invalid_execution_mode_fails_before_trigger(db_session, monkeypatch):
    from app.services import workflow_engine as we_module

    called = False

    async def fake_trigger(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(we_module.workflow_engine, "trigger_workflow", fake_trigger)

    with pytest.raises(ValueError, match="execution_mode"):
        await SubWorkflowExecutor().execute(
            input_data={},
            step_definition={"workflow_id": 1, "execution_mode": "later"},
            db=db_session,
        )
    assert called is False


@pytest.mark.asyncio
async def test_async_launch_error_fails_parent_step(db_session, monkeypatch):
    from app.services import workflow_engine as we_module

    async def failing_trigger(*args, **kwargs):
        raise ValueError("workflow is inactive")

    monkeypatch.setattr(we_module.workflow_engine, "trigger_workflow", failing_trigger)

    with pytest.raises(ValueError, match="inactive"):
        await SubWorkflowExecutor().execute(
            input_data={},
            step_definition={
                "workflow_id": 1,
                "execution_mode": "async",
                "input_data": {},
            },
            db=db_session,
        )


@pytest.mark.asyncio
async def test_default_sync_mode_still_waits_and_merges_output(db_session, monkeypatch):
    """Existing (no execution_mode) workflows keep the sync call/wait/merge path."""
    from app.services import workflow_engine as we_module

    wf, child = await _seed_child(db_session, name="sub-sync")
    child.status = "completed"
    child.output_data = {"answer": 42}
    await db_session.flush()

    async def fake_trigger(db, workflow_id, run_data):
        return child

    waited = {}

    async def fake_wait(db, run_id, timeout):
        waited.update(run_id=run_id, timeout=timeout)
        return None

    monkeypatch.setattr(we_module.workflow_engine, "trigger_workflow", fake_trigger)
    executor = SubWorkflowExecutor()
    monkeypatch.setattr(executor, "_wait_for_run_completion", fake_wait)

    result = await executor.execute(
        input_data={},
        step_definition={
            "workflow_id": wf.id,
            "input_data": {},
            "timeout_seconds": 17,
        },
        db=db_session,
    )

    assert waited == {"run_id": child.id, "timeout": 17}
    assert result["success"] is True
    assert result["result_data"] == {"answer": 42}
    assert "execution_mode" not in result


@pytest.mark.asyncio
async def test_explicit_sync_mode_also_waits(db_session, monkeypatch):
    from app.services import workflow_engine as we_module

    wf, child = await _seed_child(db_session, name="sub-explicit-sync")
    child.status = "completed"
    child.output_data = {}
    await db_session.flush()

    async def fake_trigger(db, workflow_id, run_data):
        return child

    waited = False

    async def fake_wait(db, run_id, timeout):
        nonlocal waited
        waited = True

    monkeypatch.setattr(we_module.workflow_engine, "trigger_workflow", fake_trigger)
    executor = SubWorkflowExecutor()
    monkeypatch.setattr(executor, "_wait_for_run_completion", fake_wait)

    result = await executor.execute(
        input_data={},
        step_definition={
            "workflow_id": wf.id,
            "execution_mode": "SYNC",  # case-normalized
            "input_data": {},
        },
        db=db_session,
    )

    assert waited is True
    assert result["success"] is True

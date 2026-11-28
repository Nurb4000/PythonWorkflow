"""
Regression test for the SubWorkflowExecutor result-source bug (Feature-Plan §2.1).

``SubWorkflowExecutor.execute()`` returns the sub-run's final output under the
``result_data`` key of its return dict. The original code read that value from
``final_run.result_data`` -- but ``WorkflowRun`` has no ``result_data`` column
(that column belongs to the ``Task`` model). Every successful sub-workflow thus
raised ``AttributeError: 'WorkflowRun' object has no attribute 'result_data'``.

The fix reads ``final_run.output_data`` (the column that actually holds a run's
final output). This test pins that behavior: it seeds a completed sub-run with a
known ``output_data`` and asserts the executor surfaces it unchanged. On the
buggy code the call raises AttributeError; after the fix it returns the output.
"""
import pytest

from app.models.schemas import Workflow, WorkflowRun
from app.services.step_executors import SubWorkflowExecutor


@pytest.fixture
async def db_session(db_engine):
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.ext.asyncio import AsyncSession

    async_session = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


@pytest.mark.asyncio
async def test_execute_returns_subrun_output_data(db_session, monkeypatch):
    """A completed sub-run's ``output_data`` flows back as the step result."""
    from app.services import workflow_engine as workflow_engine_module

    # Seed a completed sub-run with known output.
    wf = Workflow(name="sub-output")
    db_session.add(wf)
    await db_session.flush()
    expected_output = {"answer": 42, "labels": ["x", "y"]}
    sub_run = WorkflowRun(
        workflow_id=wf.id,
        status="completed",
        output_data=expected_output,
    )
    db_session.add(sub_run)
    await db_session.flush()

    async def fake_trigger(db, workflow_id, run_data):
        return sub_run

    # The sub-run is already terminal, so the synchronous wait is a no-op.
    async def fake_wait(db, run_id, timeout):
        return None

    monkeypatch.setattr(workflow_engine_module.workflow_engine, "trigger_workflow", fake_trigger)

    executor = SubWorkflowExecutor()
    monkeypatch.setattr(executor, "_wait_for_run_completion", fake_wait)

    result = await executor.execute(
        input_data={"_workflow_run_id": 7},
        step_definition={
            "workflow_id": wf.id,
            "input_data": {},
            "timeout_seconds": 5,
        },
        db=db_session,
    )

    assert result["success"] is True
    assert result["status"] == "completed"
    assert result["run_id"] == sub_run.id
    # The key assertion: output surfaces under the result_data key.
    assert result["result_data"] == expected_output


@pytest.mark.asyncio
async def test_execute_handles_empty_output_data(db_session, monkeypatch):
    """A completed sub-run with no output yields an empty dict, not a crash."""
    from app.services import workflow_engine as workflow_engine_module

    wf = Workflow(name="sub-empty")
    db_session.add(wf)
    await db_session.flush()
    sub_run = WorkflowRun(workflow_id=wf.id, status="completed", output_data={})
    db_session.add(sub_run)
    await db_session.flush()

    async def fake_trigger(db, workflow_id, run_data):
        return sub_run

    async def fake_wait(db, run_id, timeout):
        return None

    monkeypatch.setattr(workflow_engine_module.workflow_engine, "trigger_workflow", fake_trigger)
    executor = SubWorkflowExecutor()
    monkeypatch.setattr(executor, "_wait_for_run_completion", fake_wait)

    result = await executor.execute(
        input_data={},
        step_definition={"workflow_id": wf.id, "input_data": {}, "timeout_seconds": 5},
        db=db_session,
    )

    assert result["success"] is True
    assert result["result_data"] == {}


@pytest.mark.asyncio
async def test_execute_raises_on_failed_subrun(db_session, monkeypatch):
    """M6: a failed child run must surface as a failed parent step.

    Returning ``{"success": False}`` made the engine mark the parent step
    completed, so on-failure routing and try_catch never saw the failure.
    """
    from app.services import workflow_engine as workflow_engine_module

    wf = Workflow(name="sub-failed")
    db_session.add(wf)
    await db_session.flush()
    sub_run = WorkflowRun(
        workflow_id=wf.id,
        status="failed",
        error_message="child exploded",
    )
    db_session.add(sub_run)
    await db_session.flush()

    async def fake_trigger(db, workflow_id, run_data):
        return sub_run

    async def fake_wait(db, run_id, timeout):
        return None

    monkeypatch.setattr(workflow_engine_module.workflow_engine, "trigger_workflow", fake_trigger)
    executor = SubWorkflowExecutor()
    monkeypatch.setattr(executor, "_wait_for_run_completion", fake_wait)

    with pytest.raises(RuntimeError, match="child exploded"):
        await executor.execute(
            input_data={},
            step_definition={
                "workflow_id": wf.id,
                "input_data": {},
                "timeout_seconds": 5,
            },
            db=db_session,
        )

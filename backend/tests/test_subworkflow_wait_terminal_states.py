"""
Regression tests for the SubWorkflowExecutor synchronous-wait terminal-state
handling (deep bug-hunt lead #1).

The parent executor blocks in ``_wait_for_run_completion`` until the sub-run
reaches a terminal state. The engine's own terminal set
(``workflow_engine._execute_workflow``) is ``(completed, failed, timeout,
cancelled)`` and a run can also legitimately sit at ``waiting`` while paused at
a human step. The parent wait loop must recognize those states instead of
spinning until a spurious parent-side timeout.
"""
import asyncio

import pytest

from app.models.auth import User
from app.models.schemas import Workflow, WorkflowRun
from app.services.step_executors import SubWorkflowExecutor


@pytest.fixture
async def db_session(db_engine):
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.ext.asyncio import AsyncSession

    async_session = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


async def _seed_run(db, status: str):
    wf = Workflow(name=f"sub-{status}")
    db.add(wf)
    await db.flush()
    run = WorkflowRun(workflow_id=wf.id, status=status)
    db.add(run)
    await db.flush()
    return run


@pytest.mark.asyncio
async def test_wait_loop_treats_timeout_run_as_terminal(db_session):
    """A sub-run that genuinely timed out (status 'timeout') is done. The parent
    must return immediately, not poll until a misleading parent-side timeout."""
    run = await _seed_run(db_session, "timeout")
    result = await SubWorkflowExecutor()._wait_for_run_completion(
        db_session, run.id, timeout=1
    )
    assert result is None


@pytest.mark.asyncio
async def test_wait_loop_treats_waiting_run_as_terminal(db_session):
    """A sub-run paused at a human step (status 'waiting') is a legitimate end
    state for a synchronous wait. The parent returns it honestly instead of
    spinning to a fake timeout after the default 300s window."""
    run = await _seed_run(db_session, "waiting")
    result = await SubWorkflowExecutor()._wait_for_run_completion(
        db_session, run.id, timeout=1
    )
    assert result is None


@pytest.mark.asyncio
async def test_wait_loop_still_waits_for_incomplete_run(db_session):
    """Sanity: a still-running run is NOT terminal — the loop keeps polling and
    eventually raises TimeoutError against the (short) parent timeout."""
    run = await _seed_run(db_session, "running")
    with pytest.raises(asyncio.TimeoutError):
        await SubWorkflowExecutor()._wait_for_run_completion(
            db_session, run.id, timeout=1
        )

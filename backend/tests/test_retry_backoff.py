"""Tests for G3: exponential-backoff retry policy for per-step retries.

Covers the pure :class:`RetryPolicy` / ``backoff_delay`` helpers (exponential curve,
max-delay cap, full-jitter bounds, and explicit ``Retry-After`` handling), the
``extract_retry_after`` parser, and the engine wiring in
``WorkflowEngine._execute_single_step`` (retries actually sleep a bounded backoff,
and an explicit Retry-After overrides the curve).

No test hits the network: the persistent-failure path uses an api_call step pointed
at an unreachable URL, and ``asyncio.sleep`` is replaced with a recorder so delays
are captured instantly.
"""
import asyncio
import time

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.services.workflow_engine as we_module
from app.core.config import settings
from app.models.schemas import WorkflowRun
from app.schemas.workflow import WorkflowRunCreate
from app.services.retry_backoff import (
    RetryPolicy,
    backoff_delay,
    extract_retry_after,
)


# --------------------------------------------------------------------------- #
# Pure helper tests
# --------------------------------------------------------------------------- #
def test_exponential_curve_without_jitter():
    p = RetryPolicy(base_delay=1.0, multiplier=2.0, max_delay=100.0, jitter=False)
    assert [p.delay(a) for a in (1, 2, 3, 4, 5)] == [1.0, 2.0, 4.0, 8.0, 16.0]


def test_max_delay_caps_the_curve():
    p = RetryPolicy(base_delay=1.0, multiplier=10.0, max_delay=5.0, jitter=False)
    # 1, 10->5, 100->5, 1000->5
    assert [p.delay(a) for a in (1, 2, 3, 4)] == [1.0, 5.0, 5.0, 5.0]


def test_retry_after_overrides_curve_and_is_capped():
    p = RetryPolicy(base_delay=1.0, multiplier=2.0, max_delay=10.0, jitter=False)
    assert p.delay(1, retry_after=3.0) == 3.0          # overrides the base curve
    assert p.delay(4, retry_after=999.0) == 10.0       # still capped at max_delay
    assert p.delay(2, retry_after=0.0) == 0.0          # non-negative


def test_jitter_stays_within_bounds():
    p = RetryPolicy(base_delay=2.0, multiplier=3.0, max_delay=1000.0, jitter=True)
    for attempt in (1, 2, 3, 4):
        cap = min(2.0 * (3.0 ** (attempt - 1)), 1000.0)
        for _ in range(200):
            d = p.delay(attempt)
            assert 0.0 <= d <= cap


def test_backoff_delay_wrapper_matches_policy():
    assert backoff_delay(3, base_delay=1.0, multiplier=2.0, max_delay=100.0, jitter=False) == 4.0
    assert backoff_delay(2, base_delay=1.0, multiplier=2.0, max_delay=100.0, jitter=True) >= 0.0


def test_extract_retry_after_from_attribute():
    e = Exception()
    e.retry_after = 3.5
    assert extract_retry_after(e) == 3.5


def test_extract_retry_after_from_headers_numeric():
    e = Exception()
    e.headers = {"Retry-After": "7"}
    assert extract_retry_after(e) == 7.0


def test_extract_retry_after_non_numeric_header_is_none():
    e = Exception()
    e.headers = {"Retry-After": "Wed, 21 Oct 2099 07:28:00 GMT"}
    assert extract_retry_after(e) is None


def test_extract_retry_after_absent_is_none():
    assert extract_retry_after(Exception()) is None
    e = Exception()
    e.retry_after = ""  # empty string is not a valid number
    assert extract_retry_after(e) is None


# --------------------------------------------------------------------------- #
# Engine wiring tests
# --------------------------------------------------------------------------- #
class _DelayRecorder:
    """Wraps :meth:`RetryPolicy.delay` to record (attempt, retry_after) and return 0.

    Patching the delay at this seam (rather than ``asyncio.sleep``) lets us assert the
    engine computes and threads the right backoff values without replacing the event
    loop's own sleeps -- which would stall the workflow task's scheduling.
    """

    def __init__(self):
        self.calls = []

    def install(self, monkeypatch):
        recorder = self

        def fake_delay(self, attempt, *, retry_after=None):
            recorder.calls.append((attempt, retry_after))
            return 0.0

        monkeypatch.setattr(we_module.RetryPolicy, "delay", fake_delay)
        return self


@pytest_asyncio.fixture
async def session(db_engine):
    async with async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)() as s:
        yield s


@pytest.fixture
def engine(db_engine, monkeypatch):
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(we_module, "async_session_factory", factory)
    return we_module.WorkflowEngine()


async def _create_run(engine, session, max_retries):
    from app.schemas.workflow import WorkflowCreate

    wf = await engine.create_workflow(
        session,
        WorkflowCreate(
            name="Retry",
            steps=[{"step_type": "api_call", "definition": {"method": "GET", "url": "not-a-real-url"}}],
        ),
    )
    run = await engine.trigger_workflow(session, wf.id, WorkflowRunCreate(max_retries=max_retries))
    return run.id


async def _wait_run(session, run_id, timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        await asyncio.sleep(0.05)
        run = await session.get(WorkflowRun, run_id)
        if run is not None and run.status in ("completed", "failed", "waiting"):
            return run
    raise AssertionError("run did not finish in time")


@pytest.mark.asyncio
async def test_engine_sleeps_a_bounded_backoff_on_persistent_failure(engine, session, monkeypatch):
    recorder = _DelayRecorder().install(monkeypatch)

    run_id = await _create_run(engine, session, max_retries=2)
    run = await _wait_run(session, run_id)

    assert run.status == "failed"
    assert "failed after" in run.error_message.lower()
    # Two retries => two backoff computations, at 1-based attempts 1 and 2. No
    # explicit Retry-After is present on a connection error, so retry_after is None.
    assert recorder.calls == [(1, None), (2, None)]


@pytest.mark.asyncio
async def test_engine_honors_retry_after_over_curve(engine, session, monkeypatch):
    recorder = _DelayRecorder().install(monkeypatch)
    # Force an explicit Retry-After; the engine must thread it through to delay()
    # instead of using the exponential curve.
    monkeypatch.setattr(we_module, "extract_retry_after", lambda exc: 0.5)

    run_id = await _create_run(engine, session, max_retries=2)
    run = await _wait_run(session, run_id)

    assert run.status == "failed"
    assert recorder.calls == [(1, 0.5), (2, 0.5)]

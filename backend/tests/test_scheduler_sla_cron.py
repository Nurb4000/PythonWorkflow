"""
Regression tests for scheduler findings I1 and I2.

I1: 6-field crons (with seconds) are now registered instead of silently
    dropped, and malformed expressions raise a surfaced error rather than being
    ignored.
I2: an SLA response is only breached when elapsed time is strictly greater than
    the target (>100%); a run responding exactly at its deadline is not flagged.
"""
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.services.scheduler as sched_mod
from app.services.scheduler import SchedulerService
from app.models.schemas import WorkflowRun

FIXED_NOW = datetime(2030, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


class _Clock(datetime):
    """A datetime subclass whose ``now()`` always returns FIXED_NOW."""

    @classmethod
    def now(cls, tz=None):
        return FIXED_NOW


@pytest.fixture
def service(db_engine):
    svc = SchedulerService()
    svc.db_session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    return svc


async def _insert_run(engine, started_at, target_hours, status="running"):
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
        run = WorkflowRun(
            status=status,
            triggered_by="schedule",
            started_at=started_at,
            sla_response_target_hours=target_hours,
            sla_response_met=None,
        )
        db.add(run)
        await db.commit()
    return run.id


async def _get_run(engine, run_id):
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
        return await db.get(WorkflowRun, run_id)


# --- I2: SLA breach boundary ----------------------------------------------------

@pytest.mark.asyncio
async def test_sla_not_breached_at_exact_target(db_engine, service, monkeypatch, caplog):
    from app.services import email_service
    monkeypatch.setattr(sched_mod, "datetime", _Clock)
    monkeypatch.setattr(email_service, "notify_admin", lambda *a, **k: None)

    run_id = await _insert_run(db_engine, FIXED_NOW - timedelta(hours=5), target_hours=5)

    # If the check raised internally it would be swallowed and logged; assert
    # that did not happen so the "not breached" result is meaningful.
    with caplog.at_level(logging.ERROR, logger="app.services.scheduler"):
        await service._check_sla_breaches()

    run = await _get_run(db_engine, run_id)
    assert run.sla_response_met is None  # exactly at target -> NOT breached
    assert "SLA breach check failed" not in caplog.text


@pytest.mark.asyncio
async def test_sla_breached_when_past_target(db_engine, service, monkeypatch, caplog):
    from app.services import email_service
    monkeypatch.setattr(sched_mod, "datetime", _Clock)
    monkeypatch.setattr(email_service, "notify_admin", lambda *a, **k: None)

    run_id = await _insert_run(db_engine, FIXED_NOW - timedelta(hours=6), target_hours=5)

    with caplog.at_level(logging.ERROR, logger="app.services.scheduler"):
        await service._check_sla_breaches()

    run = await _get_run(db_engine, run_id)
    assert run.sla_response_met is False  # 6h elapsed > 5h target -> breached
    assert "SLA breach check failed" not in caplog.text


# --- I1: cron parsing -----------------------------------------------------------

def test_six_field_cron_registers_job(service):
    ns = SimpleNamespace(id=7, workflow_id=1, cron_expression="0 0 0 1 1 1")
    service._add_schedule_job(ns)
    assert service.scheduler.get_job("schedule_7") is not None


def test_five_field_cron_registers_job(service):
    ns = SimpleNamespace(id=8, workflow_id=1, cron_expression="0 0 1 1 1")
    service._add_schedule_job(ns)
    assert service.scheduler.get_job("schedule_8") is not None


def test_invalid_cron_field_count_logs_error(service, caplog):
    ns = SimpleNamespace(id=9, workflow_id=1, cron_expression="* * *")
    with caplog.at_level(logging.ERROR, logger="app.services.scheduler"):
        service._add_schedule_job(ns)
    assert "Failed to add schedule job" in caplog.text
    assert service.scheduler.get_job("schedule_9") is None

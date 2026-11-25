"""
Regression test for findings #22 (`get_active_schedules` crashed on monitor jobs).

`initialize()` registers permanent monitor jobs with ids `sla_breach_monitor` and
`date_target_breach_monitor`. `get_active_schedules` did
`int(job.id.replace("schedule_", ""))` for every job; those monitor ids have no
numeric suffix, so `int(...)` raised ValueError and the method never returned —
breaking `/health` (always reports scheduler unhealthy) and `/schedules/status`
(guaranteed HTTP 500, unauthenticated).

Fix: skip any job whose id is not a `schedule_<n>` before parsing the int.

Uses fake APScheduler jobs so no live scheduler/DB is required.
"""
import asyncio
from datetime import datetime, timezone

import pytest

from app.services.scheduler import SchedulerService


class _FakeJob:
    def __init__(self, job_id, next_run_time=None):
        self.id = job_id
        self.next_run_time = next_run_time


class _FakeScheduler:
    def __init__(self, jobs):
        self._jobs = jobs

    def get_jobs(self):
        return list(self._jobs)


def _make_scheduler(jobs):
    sched = SchedulerService.__new__(SchedulerService)  # bypass __init__ (no DB/deps)
    sched.scheduler = _FakeScheduler(jobs)
    return sched


def _jobs():
    run_at = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    return [
        _FakeJob("schedule_1", run_at),
        _FakeJob("sla_breach_monitor", None),              # monitor: no numeric id
        _FakeJob("schedule_2", run_at),
        _FakeJob("date_target_breach_monitor", None),      # monitor: no numeric id
    ]


def test_get_active_schedules_skips_monitors():
    sched = _make_scheduler(_jobs())
    result = sched.get_active_schedules()
    # Only the two real schedules survive; monitors are skipped, no ValueError.
    assert [s["id"] for s in result] == [1, 2]
    assert all(s["job_id"].startswith("schedule_") for s in result)


def test_get_active_schedules_empty_when_only_monitors():
    sched = _make_scheduler([
        _FakeJob("sla_breach_monitor", None),
        _FakeJob("date_target_breach_monitor", None),
    ])
    result = sched.get_active_schedules()
    assert result == []


def test_get_active_schedules_handles_non_numeric_suffix():
    # Defensive: a schedule_ id that isn't purely numeric must not crash either.
    run_at = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    sched = _make_scheduler([
        _FakeJob("schedule_abc", run_at),
        _FakeJob("schedule_3", run_at),
    ])
    result = sched.get_active_schedules()
    assert [s["id"] for s in result] == [3]

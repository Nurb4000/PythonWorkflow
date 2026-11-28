"""F2: blocking SMTP admin notices must not stall the asyncio event loop.

Async workflow-engine and scheduler paths previously called ``notify_admin``
directly; smtplib can block for 10s per connect/TLS/login/send stage. The
helper under test runs the sender in the default thread executor while keeping
the best-effort (never raises) contract.
"""
import asyncio
import threading
import time

import pytest

from app.services import email_service


@pytest.mark.asyncio
async def test_admin_notice_runs_in_executor_thread(monkeypatch):
    threads = []

    def fake_notify(subject, body):
        threads.append(threading.current_thread())
        return True

    monkeypatch.setattr(email_service, "notify_admin", fake_notify)
    result = await email_service.run_email_in_executor(
        email_service.notify_admin, "Subject", "Body"
    )

    assert result is True
    assert len(threads) == 1
    assert threads[0] is not threading.main_thread()


@pytest.mark.asyncio
async def test_event_loop_keeps_ticking_during_blocking_send(monkeypatch):
    def slow_notify(subject, body):
        time.sleep(0.05)  # stands in for blocking SMTP connect/TLS/send
        return True

    monkeypatch.setattr(email_service, "notify_admin", slow_notify)
    ticks = 0
    running = True

    async def ticker():
        nonlocal ticks
        while running:
            ticks += 1
            await asyncio.sleep(0.001)

    tick_task = asyncio.create_task(ticker())
    try:
        result = await asyncio.wait_for(
            email_service.run_email_in_executor(
                email_service.notify_admin, "Subject", "Body"
            ),
            timeout=5,
        )
    finally:
        running = False
        await tick_task

    assert result is True
    assert ticks > 0


@pytest.mark.asyncio
async def test_executor_helper_never_raises():
    def boom(subject, body):
        raise RuntimeError("unexpected")

    assert await email_service.run_email_in_executor(boom, "Subject", "Body") is False

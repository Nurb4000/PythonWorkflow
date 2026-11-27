"""Exponential-backoff retry policy for per-step retries (G3).

Per-step retries previously used a single fixed delay (``step.retry_delay_seconds``),
so transient failures (upstream rate-limiting / throttling / brief unavailability)
re-hit the same limit and waste budget. This module computes a backoff delay with
exponential growth, optional full-jitter spread, a hard cap, and honors an explicit
``Retry-After`` from the failure (e.g. an HTTP 429/503 response).

The helpers are pure and dependency-free so they can be unit-tested in isolation;
the engine wires a :class:`RetryPolicy` (built from settings) into
``_execute_single_step``.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional


@dataclass
class RetryPolicy:
    """Retry backoff configuration.

    ``base_delay`` is the delay for the first retry; each subsequent retry grows it
    by ``multiplier`` up to ``max_delay``. With ``jitter`` enabled the actual wait is
    a uniform random value in ``[0, computed]`` (AWS 'FullJitter') so concurrent
    producers don't synchronize their retries and thundering-herd on recovery.
    """

    base_delay: float = 1.0
    multiplier: float = 2.0
    max_delay: float = 60.0
    jitter: bool = True

    def delay(self, attempt: int, *, retry_after: Optional[float] = None) -> float:
        """Return the sleep seconds before 1-based ``attempt``.

        An explicit ``retry_after`` (seconds, from a ``Retry-After`` header or a
        ``.retry_after`` attribute) takes precedence and is still capped at
        ``max_delay``. Otherwise an exponential-with-jitter delay is returned.
        """
        if retry_after is not None:
            return max(0.0, min(float(retry_after), self.max_delay))

        capped = min(self.base_delay * (self.multiplier ** (attempt - 1)), self.max_delay)
        if not self.jitter:
            return capped
        return random.uniform(0, capped)


def extract_retry_after(exc: BaseException) -> Optional[float]:
    """Best-effort extraction of a ``Retry-After`` delay (seconds) from an exception.

    Checks a ``.retry_after`` attribute first, then an ``httpx``-style ``headers``
    mapping (values may be numeric seconds or an HTTP-date string; only numeric
    values are honored). Returns ``None`` when nothing usable is present.
    """
    explicit = getattr(exc, "retry_after", None)
    if explicit is not None:
        return _to_float(explicit)

    headers = getattr(exc, "headers", None)
    if headers is not None:
        value = headers.get("Retry-After") if hasattr(headers, "get") else None
        if value is not None:
            return _to_float(value)
    return None


def _to_float(value: object) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def backoff_delay(
    attempt: int,
    base_delay: float = 1.0,
    multiplier: float = 2.0,
    max_delay: float = 60.0,
    jitter: bool = True,
) -> float:
    """Convenience wrapper over :meth:`RetryPolicy.delay` for direct calls/tests."""
    return RetryPolicy(
        base_delay=base_delay,
        multiplier=multiplier,
        max_delay=max_delay,
        jitter=jitter,
    ).delay(attempt)

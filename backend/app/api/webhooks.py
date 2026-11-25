"""
API endpoints for webhooks and external triggers (P2.5)
"""
import hmac
import time
from collections import OrderedDict, defaultdict
from fastapi import APIRouter, HTTPException, Header, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from app.core.database import get_db
from app.core.config import settings
from app.services.scheduler import scheduler_service
from app.services.auth_service import auth_service
from app.models.schemas import Workflow

router = APIRouter()

# Simple in-memory rate limiter: max requests per source IP per window
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = 120    # requests per window
_rate_buckets: dict[str, list[float]] = defaultdict(list)

# FG5: Idempotency — track idempotency keys for 15 minutes
_IDEMPOTENCY_WINDOW = 900  # seconds
# Hard cap on distinct idempotency keys held at once (findings #37). The cache is keyed
# on a client-controlled header, so an attacker flooding unique X-Idempotency-Key values
# can no longer grow it without limit. 10k comfortably exceeds any single source's
# 120 req/min * 15 min budget while bounding memory and the per-request scan cost.
_IDEMPOTENCY_MAX_ENTRIES = 10_000
# OrderedDict keeps insertion order, so the oldest key is always at the front — enabling
# O(1) oldest-first eviction. Bounded size bounds both memory and the per-request scan
# cost (findings #37): a flood of attacker-controlled X-Idempotency-Key headers can no
# longer grow the cache without limit.
_idempotency_cache: "OrderedDict[str, tuple[float, int]]" = OrderedDict()


def _prune_idempotency_entries(now: float) -> None:
    """Drop expired entries, then evict oldest beyond the hard cap (findings #37).

    The cache is keyed on a client-controlled header and was only lazily pruned (and
    never evicted on overflow), so a flood of unique keys grew it without bound and
    made each scan O(N). Pruning on every access + a hard LRU cap keeps N bounded
    regardless of request pattern. Entries are inserted in monotonic-time order, so the
    front is always the oldest.
    """
    cutoff = now - _IDEMPOTENCY_WINDOW
    while _idempotency_cache and next(iter(_idempotency_cache.values()))[0] < cutoff:
        _idempotency_cache.popitem(last=False)
    while len(_idempotency_cache) > _IDEMPOTENCY_MAX_ENTRIES:
        _idempotency_cache.popitem(last=False)


def _record_idempotency(key: str, run_id: int) -> None:
    """Store a (now, run_id) entry and evict oldest beyond the hard cap (#37)."""
    _idempotency_cache[key] = (time.monotonic(), run_id)
    _idempotency_cache.move_to_end(key)  # most-recently-used goes to the back
    while len(_idempotency_cache) > _IDEMPOTENCY_MAX_ENTRIES:
        _idempotency_cache.popitem(last=False)


def _check_rate_limit(key: str) -> None:
    """Raise 429 if rate limit exceeded for the given key."""
    now = time.monotonic()
    bucket = _rate_buckets[key]
    # Prune old entries
    cutoff = now - _RATE_LIMIT_WINDOW
    while bucket and bucket[0] < cutoff:
        bucket.pop(0)
    if len(bucket) >= _RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="Rate limit exceeded (120 req/min)")
    bucket.append(now)


def verify_webhook_secret(x_webhook_secret: Optional[str]) -> None:
    """Verify the webhook secret.

    Fail closed (findings #30): if no secret is configured, reject the trigger
    instead of silently allowing unauthenticated workflow triggering. Previously
    an empty ``WEBHOOK_SECRET`` meant anyone who knew a ``workflow_id`` could run
    any active workflow anonymously — including ``custom_code`` steps (finding #1,
    OS command execution) or network/DB steps (exfiltration, SSRF, DoS).
    """
    if not settings.webhook_secret:
        raise HTTPException(
            status_code=401,
            detail="Webhook secret not configured; set WEBHOOK_SECRET to enable webhooks",
        )

    if not x_webhook_secret:
        raise HTTPException(status_code=401, detail="Missing webhook secret")

    if not hmac.compare_digest(x_webhook_secret, settings.webhook_secret):
        raise HTTPException(status_code=403, detail="Invalid webhook secret")


@router.post("/webhook/{workflow_id}")
async def webhook_trigger(
    workflow_id: int,
    payload: dict,
    x_webhook_secret: Optional[str] = Header(None),
    x_forwarded_for: Optional[str] = Header(None),
    x_idempotency_key: Optional[str] = Header(None),
    request: Request = None,
    db: AsyncSession = Depends(get_db)
):
    """Trigger a workflow via webhook"""

    # M6 fix: key rate-limit on transport socket IP (proxy allowlist) or
    # authenticated principal, not the spoofable X-Forwarded-For header.
    if request and request.client:
        client_ip = request.client.host
    else:
        client_ip = (x_forwarded_for or "unknown").split(",")[0].strip()
    _check_rate_limit(f"webhook:{client_ip}")

    # Verify webhook secret if configured. Must run before the idempotency check so an
    # attacker with a bad/missing secret cannot drive cache writes / O(N) scans
    # (findings #37).
    verify_webhook_secret(x_webhook_secret)

    # FG5: Idempotency check — after auth (#37): prune expired + evict-overflow, then
    # replay a previously seen key.
    if x_idempotency_key:
        _prune_idempotency_entries(time.monotonic())
        cached = _idempotency_cache.get(x_idempotency_key)
        if cached is not None:
            return {
                "success": True,
                "run_id": cached[1],
                "workflow_id": workflow_id,
                "message": "Duplicate request (idempotent replay)",
                "idempotent": True,
            }
    
    try:
        # Verify workflow exists and is active
        stmt = select(Workflow).where(Workflow.id == workflow_id, Workflow.is_active == True)
        result = await db.execute(stmt)
        workflow = result.scalar_one_or_none()
        
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found or inactive")
        
        # Trigger the workflow via scheduler (which uses engine.trigger_workflow)
        run = await scheduler_service.trigger_webhook(workflow_id, payload)

        # Store idempotency key (bounded, oldest-first eviction — findings #37)
        if x_idempotency_key:
            _record_idempotency(x_idempotency_key, run.id)

        return {
            "success": True,
            "run_id": run.id,
            "workflow_id": workflow_id,
            "message": "Workflow triggered successfully"
        }
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Webhook trigger failed: {str(e)}")


@router.post("/api/trigger/{workflow_id}")
async def external_trigger(
    workflow_id: int,
    input_data: dict,
    x_api_key: Optional[str] = Header(None),
    x_forwarded_for: Optional[str] = Header(None),
    request: Request = None,
    db: AsyncSession = Depends(get_db)
):
    """Trigger a workflow via external API"""

    # M6 fix: key rate-limit on transport socket IP, not spoofable X-Forwarded-For
    if request and request.client:
        client_ip = request.client.host
    else:
        client_ip = (x_forwarded_for or "unknown").split(",")[0].strip()
    _check_rate_limit(f"api_trigger:{client_ip}")

    # Validate API key against stored tokens if provided.
    # Findings #31 fix: verify with bcrypt via the shared indexed lookup
    # (auth_service.verify_api_token) instead of comparing an unsalted SHA-256
    # hash against the bcrypt-stored token_hash — the two can never match, which
    # made this endpoint return 401 for every request (valid or not). verify_api_token
    # also handles expiry (tz-aware) and returns None for unknown/inactive tokens.
    if x_api_key:
        user = await auth_service.verify_api_token(db, x_api_key)
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid API key")
    else:
        raise HTTPException(status_code=401, detail="Missing X-Api-Key header")

    try:
        # Verify workflow exists and is active
        stmt = select(Workflow).where(Workflow.id == workflow_id, Workflow.is_active == True)
        result = await db.execute(stmt)
        workflow = result.scalar_one_or_none()
        
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found or inactive")
        
        # Trigger the workflow via scheduler
        run = await scheduler_service.trigger_external_api(workflow_id, input_data, x_api_key)
        
        return {
            "success": True,
            "run_id": run.id,
            "workflow_id": workflow_id,
            "message": "Workflow triggered successfully"
        }
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"API trigger failed: {str(e)}")


@router.get("/schedules/status")
async def get_schedule_status():
    """Get status of all active schedules"""
    schedules = scheduler_service.get_active_schedules()
    return {
        "active_schedules": len(schedules),
        "schedules": schedules
    }



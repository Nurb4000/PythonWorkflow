# PythonWorkflow ("Instant Workflow") — Feature-Gap & Status Review

**Date:** 2026-11-26
**Repo:** `/workspace` (git root; GitHub `Nurb4000/PythonWorkflow`, branch `main`)
**Purpose:** Track feature-gap items from the original gap review and record resolution status as work is completed.

## Priority order for remaining work
`M5` → `G4` → `G5` → `M4/M3/G6/M6/M2` → `M7/M8/M9`

---

## Resolution log (newest first)

### M5 — API/AI rate limiting — **RESOLVED** ✅ (2026-11-26)
- **Commit:** `867bd89` — "M5: Add per-IP API rate limiting for AI/data-query/data-export endpoints" (pushed to `main`, in sync with `origin/main`).
- **Gap it closes:** Rate limiting previously existed only for login brute-force protection (`POST /auth/login`). The high-cost / high-touch routers `/ai/*`, `/data-query/*`, and `/data-export/*` were unbounded — an abuse/DoS surface and, for AI, spend-exposed LLM calls.
- **What was added:**
  - New `backend/app/services/rate_limiter.py`: a shared per-IP sliding-window limiter plus a FastAPI dependency that returns HTTP 429 with a `Retry-After` header when a source IP exceeds the window.
  - Config: `api_requests_per_window` / `api_request_window_seconds` (default 60/60s), env-configurable.
  - Wired the limiter onto the `ai`, `data_query`, and `data_export` routers in `app/main.py`. The existing per-user AI cost throttle is retained alongside it.
- **Tests:** `backend/tests/test_rate_limiter.py` — **12 passed, 0 failed** on the remote test VM (PostgreSQL). No regressions.
- **Docs:** README updated to document rate limiting as shipped.

### G2 — Scoped variables / cross-step reference resolution — **RESOLVED** ✅
- **Commit:** `47c1e1f` — scoped variables + `{{ }}` template resolution (`backend/app/services/interpolation.py`, wired into the engine). Full suite green.

### M1 — Loop / foreach executor + designer node — **RESOLVED** ✅
- **Commit:** `48ffaca` — loop/foreach executor, engine registration, designer node + tests.

### G1 — True parallel execution + fan-in — **RESOLVED** ✅
- **Commit:** `f6faa0d` — true parallel execution + fan-in synchronization.

---

## Not yet started (next)
- **G4** — External notification channels.
- **G5** — Outgoing webhook signing + retry/idempotency.
- **M4/M3/G6/M6/M2** — Medium-tier improvements.
- **M7/M8/M9** — Lower-priority polish/robustness.

# Cleanup & Continuation Plan

**Purpose:** pick-up point after the housekeeping sessions. Read "Where things stand",
then work the backlog top-down. Keep the tree green per commit.

**Last updated:** 2026-08-23

---

## Where things stand

- Branch `master`, working tree clean. All former WIP committed as grouped feature
  commits (`652a2aa`..`f123a4c`), then maintenance commits (`4e2605f`..`1d12db8`).
- Backend test suite: **147/147 passing against PostgreSQL** (no SQLite anywhere;
  141 baseline + 6 date-target tests added across Phases 4.2-4.3),
  verified both inside the backend container and via asyncpg locally before the venv
  was removed.
- The 5 previously-untracked Alembic migrations are committed and were applied to the
  dev database during a container smoke test (single linear chain, head `j0k1l2m3n4o5`).
- Docker containers were stopped at end of session (original state). Postgres image is
  pulled; `workflow_db_test` already exists.
- There is **no host venv by design** (host only has Python 3.13; project targets 3.11
  via Docker). Backend work happens through the container.

## Completed during cleanup — do NOT redo

- [x] All WIP committed (date targets, soft-delete, KB v2, users/groups split,
      incident/change demos, SLA defaults, UI polish)
- [x] SQLite removed from tests; `backend/tests/conftest.py` owns a per-test fresh
      `public` schema on `workflow_db_test` (override via `TEST_DATABASE_URL`)
- [x] PG-invalid model defaults fixed (`func.true()/false()` → `text("true"/"false")`)
      in models/{services,cmdb,date_targets,schemas}.py
- [x] `ProgrammableDelayExecutor` raises on unknown delay type; marketplace delete
      test aligned with archive-only semantics; dead duplicate branch removed
- [x] Dead weight deleted: `switch-db.*`, tracked `test_engine_behavior.py.backup`,
      one-off scripts (`fix_project.py`, `check_imports.py`,
      `migrate_empty_condition_routes.py`)
- [x] Root-owned artifacts removed: repo-root `backend_data/`, empty
      `backend/knowledge-base/` (was silently hijacking `resolve_project_root()`),
      empty `backend/data/`; stale `frontend/dist/`
- [x] `.env.example` added; `.gitignore` covers `backend/backend_data/`
- [x] README/TESTING_GUIDE de-staled (counts, PostgreSQL-only wording, structure tree)
- [x] Completed plan docs deleted (7 of them); active plan tracked; unused
      `react-flow-renderer` uninstalled (tsc verified clean); off-spec venv removed

---

## Active work (next session)

### 1. INCIDENT_CHANGE_PLAN — Phase 4 (frontend, deferred)
See `docs/INCIDENT_CHANGE_PLAN.md`. Backend (Phases 0–3) shipped: DateTarget model,
`/date-targets` API, scheduler breach checks, calc-step `date_target_key` creation.
- ~~4.1 DateTarget admin widget~~ DONE 2026-08-23 (commit d952ad9)
- ~~4.2 Task date badge~~ DONE 2026-08-24 (DateTargetBadge on task dashboards +
  TaskDetail; batch `run_ids` filter on `/date-targets`; suite now 145 passing)
- ~~4.3 Run-inspector date display~~ DONE 2026-08-24 (Date Targets card + node
  chips via stamped step_id; Phase 4 complete; suite now 147 passing)

## Backlog (prioritized)

### P1 — correctness / quick wins
0. ~~**test_marketplace.py breaks whole suite**~~ → folded into the SQLite
   purge below (FOUND 2026-08-24: 45 errors + 3 failures all from this one
   file — it hardcodes `sqlite+aiosqlite:///:memory:` and `aiosqlite` isn't
   installed, so collection errors cascade; suite otherwise healthy).
1. **Purge SQLite support entirely** (decided 2026-08-24): SQLite was the
   original dev-install path; Docker + PostgreSQL has been the only supported
   setup for a long time. Recon shows the codebase is already clean except:
   - [ ] Port `backend/tests/test_marketplace.py` off
         `sqlite+aiosqlite:///:memory:` (line 20) onto the shared Postgres
         `db_engine` fixture convention (conftest.py) — fixes the 45 errors +
         3 failures and restores a fully green suite.
   - [ ] Grep for stragglers after (`sqlite`, `aiosqlite`) in backend/, docs/,
         Makefile, compose files — currently zero outside this plan file.
   - [ ] State the policy where contributors look: one line in README +
         TESTING_GUIDE ("PostgreSQL via Docker is the only supported database;
         no SQLite fallback exists").
   - [ ] Optional belt-and-braces: fail fast at startup if `database_url`
         doesn't start with `postgresql+asyncpg://` (clear error instead of
         obscure driver failures later).
1. ~~**WorkflowDesigner.tsx debug leftovers**~~ DONE 2026-08-23: console statements
   stripped, `draggable: !readOnly` restored on start/step/end nodes, indentation normalized. (introduced during inspector WIP):
   - `console.log('[WF] handleNodeClick called:', ...)` + verbose `console.warn` in
     `handleNodeClick` — strip.
   - `buildGraph` forces `draggable: true` even in read-only run-inspector mode
     (masked only by a no-op `onNodesChange`). Restore `!readOnly` semantics and
     verify node-drag stays disabled when inspecting a run.
   - Same function block has mixed-indentation churn — normalize while there.
2. ~~**Run the E2E suite**~~ DONE 2026-08-24: all 21 checks green (smoke 8,
   designer-save 2, entry-form-task 11) against the dockerized stack. Fixes
   shipped in commit `e4611eb`; stale expectations updated for the Portal→
   Offerings rename and the TaskDetail raw-data toggle; designer-save now
   asserts the persisted A→B edge (edge count doesn't grow when wiring
   replaces an auto-connect-to-end edge). Environment notes for next run:
   - Frontend is on `:9000` — run with
     `E2E_BASE=http://localhost:9000 E2E_ADMIN_PASS=admin123 bash tests/e2e/run-e2e.sh`.
   - Dev credentials drifted from README fixtures: admin's password is the
     bootstrap `admin123` (not `admin`); `dev`/`staff` users were missing and
     have been created (username===password). `lib.js creds()` reads
     `E2E_<NAME>_USER`/`E2E_<NAME>_PASS` overrides so no DB mutation needed.
   - Fixture workflow "Test WF" was recreated via API as id 12 (old id 22 was
     gone); smoke.js takes `E2E_WF_ID`.
   - Needs host headless Chrome on 127.0.0.1:9222 (`tests/e2e/README.md`).
   Admin Users/Groups flows (post-UserManagement.tsx split) are exercised only
   indirectly by smoke.js settings checks — deeper coverage still open.
3. ~~**Decide branding once**~~ DONE 2026-08-23: "Instant Workflow" is the brand.
   Swept README/DESIGN/TESTING_GUIDE titles, frontend `<title>`, header fallback,
   Branding default, Settings placeholder, main.py docstring. Infrastructure
   identifiers (folder `PythonWorkflow`, docker image names, package.json names,
   `workflow_db`) intentionally unchanged. FastAPI title/config say "Instant Workflow"; README
   header still says "Python Workflow System". Pick one, sweep occurrences
   (`config.py`, `main.py`, `system_settings.py DEFAULT_SYSTEM_NAME`, README).

### P2 — documentation
4. **README feature coverage** for subsystems shipped but undocumented: CMDB,
   Service Catalog/SLA, Incident & Change demos, OLA tracking, KB articles,
   date targets, IMAP email ingestion, demo-data seeding. Add feature bullets +
   endpoint sections (endpoints exist in OpenAPI at `/docs`).
5. **Docs naming consistency**: lowercase reference docs (`scheduling.md`,
   `docker-deployment.md`) vs SCREAMING_CASE — standardize one style.
6. ~~**CHANGELOG maintenance entry**~~ DONE 2026-08-23 (also merged the duplicate
   `[Unreleased]` sections).

## Architecture decisions log (do not relitigate without new information)

- **2026-08-24 — Incoming email stays IMAP, no POP3 port.** Rationale:
  crash-safety (fetch → start workflow → move only after success; POP3's
  download-and-delete loses triggers on any mid-flight failure), UID-based
  dedupe across restarts, IDLE near-real-time triggering, existing working
  monitor. POP3 only becomes relevant if an upstream server offers nothing
  else — handle via small adapter IF that materializes.
- **2026-08-24 — Storage stays JSONB, no dynamic-DDL tables.** See
  SCALE_GOVERNANCE_PLAN.md "Data storage architecture".
- **2026-08-24 — Cross-workflow handoff: synchronous sub-workflow step
  first, async fire-and-forget second.** See SCALE_GOVERNANCE_PLAN.md
  Open Decision #8.

## Holes flagged during 2026-08-24 review (untriaged — scope before scheduling)

- **Secrets at rest**: `smtp_password` / `imap_password` stored plaintext in
  `system_settings` (and CI webhooks may hold credentials). At minimum
  document the exposure; consider app-level encryption with a key from env.
- **Executor authorization surface**: `CustomCodeExecutor`,
  `DatabaseQueryExecutor` (raw SQL), `APICallExecutor`, and the admin-only
  raw-SQL endpoint deserve an explicit permission matrix review (who can
  create steps that run code/SQL against the app DB? SSRF posture for
  admin-set URLs like llama_cpp_url?).
- **Backup/restore runbook**: named volumes exist (P3 item 9) but there is no
  documented, tested pg_dump/restore procedure or schedule.
- **JWT secret management**: verify `SECRET_KEY` isn't a committed default in
  prod deployments; document rotation.

### P3 — infrastructure / hygiene
7. **Python version strategy**: stay on 3.11 (current pin) or modernize. If moving to
   3.13: bump pins first (`pydantic≥2.9`, `bcrypt≥4.2` — current pins have no cp313
   wheels), switch `Dockerfile.backend` base, full container test rerun. If staying,
   document that choice here.
8. **CI**: no workflows exist. A minimal GitHub Action = postgres service container +
   `docker compose`-style backend pytest + `tsc --noEmit` would lock in today's green
   baseline.
9. ~~**Prod compose data check**~~ DONE 2026-08-23: prod override now mounts named
   volumes for `/app/uploads` + `/app/backend_data`; usage documented in
   `docs/docker-deployment.md` (override file — never run standalone).
10. **Data-dir consolidation (optional)**: three runtime dirs under `backend/`
    (`uploads/form_uploads`, `uploads/branding`, `backend_data/email_attachments`),
    all `__file__`-anchored. Could unify behind one `settings.data_dir` eventually.
    Cosmetic unless item 9 reveals a real problem.
11. **npm audit** report flagged advisories during uninstall — triage someday;
    not urgent for an internal tool.
12. **`tests/e2e/demo-shots.js`** is a screenshot demo, not a test — move to
    `scripts/demos/` or delete if nobody uses it.

---

## Environment / command notes

```bash
# Daily drivers
docker compose up -d postgres backend   # backend auto-runs alembic upgrade head
make test-backend                       # 141 tests on workflow_db_test (auto-created)
cd frontend && npx tsc --noEmit         # type check (~clean baseline today)
make db-revision MSG='...'              # autogenerate migration (throwaway DB hint inside)
```

- No host venv exists and none should be created (host Python is 3.13; project pins
  target 3.11). Container path only.
- Tests recreate the `public` schema per test — safe to re-run anytime; they never
  touch `workflow_db`.
- Git identity: `ziggy <ziggy@localhost.localdomain>` matches all history; leave as-is.

## Definition of done for any change here

1. `make test-backend` green (expect 147 passing since Phase 4 date-target tests; investigate count drift)
2. `npx tsc --noEmit` clean (if frontend touched)
3. Single Alembic head (`alembic heads` shows one revision)
4. Working tree committed with a descriptive message; no stray debug logs left in
   frontend diffs (this bit us once — see P1 item 1)

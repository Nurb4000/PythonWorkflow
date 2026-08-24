# Cleanup & Continuation Plan

**Purpose:** pick-up point after the housekeeping sessions. Read "Where things stand",
then work the backlog top-down. Keep the tree green per commit.

**Last updated:** 2026-08-23

---

## Where things stand

- Branch `master`, working tree clean. All former WIP committed as grouped feature
  commits (`652a2aa`..`f123a4c`), then maintenance commits (`4e2605f`..`1d12db8`).
- Backend test suite: **141/141 passing against PostgreSQL** (no SQLite anywhere),
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
Remaining:
- 4.1 DateTarget admin widget
- 4.2 Task date badge
- 4.3 Run-inspector date display

## Backlog (prioritized)

### P1 — correctness / quick wins
1. ~~**WorkflowDesigner.tsx debug leftovers**~~ DONE 2026-08-23: console statements
   stripped, `draggable: !readOnly` restored on start/step/end nodes, indentation normalized. (introduced during inspector WIP):
   - `console.log('[WF] handleNodeClick called:', ...)` + verbose `console.warn` in
     `handleNodeClick` — strip.
   - `buildGraph` forces `draggable: true` even in read-only run-inspector mode
     (masked only by a no-op `onNodesChange`). Restore `!readOnly` semantics and
     verify node-drag stays disabled when inspecting a run.
   - Same function block has mixed-indentation churn — normalize while there.
2. **Run the E2E suite** (hasn't been run since the users/groups page split):
   `bash tests/e2e/run-e2e.sh` (needs Chromium on 127.0.0.1:9222, see
   `tests/e2e/README.md`). Pay attention to admin Users/Groups flows that replaced
   `UserManagement.tsx`.
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

1. `make test-backend` green (expect 141 passing; investigate count drift)
2. `npx tsc --noEmit` clean (if frontend touched)
3. Single Alembic head (`alembic heads` shows one revision)
4. Working tree committed with a descriptive message; no stray debug logs left in
   frontend diffs (this bit us once — see P1 item 1)

# Run Inspector — Plan

Status: **DRAFT — no code written yet.**
Goal of this doc: keep a step-by-step plan for building a proper run-detail
viewer that renders the workflow as the same node graph used by the designer,
overlays run state (status / errors) onto each node, and lets users click a node
for full details. Existing list views are retained but gain a "open in graph"
deep-link.

Multi-session plan: each step is small, independently testable, and can be the
unit of a session. Steps are ordered to keep the system green at every point.

---

## Background / current state (verified 2026-08)

- Run detail page is `frontend/src/pages/RunMonitor.tsx` at route `/runs/:runId`.
  It fetches `GET /runs/{id}` + `GET /runs/{id}/steps` (`runApi.getRun` /
  `getRunSteps` in `frontend/src/services/api.ts:79-89`) and renders a plain
  accordion list of step instances. The "Chosen Branches" section is a stub —
  `isGraphMode` is hardcoded `true` (`RunMonitor.tsx:127-130`) and no graph is
  drawn.
- Designer `frontend/src/pages/WorkflowDesigner.tsx` (2073 lines) renders the
  graph with `react-flow-renderer`. `buildGraph` (`WorkflowDesigner.tsx:508-622`)
  builds nodes/edges from step `definition.next_step_ids/next_step_id`,
  condition `routes[]`/`default_target_step_id`, and `config.start_step_ids`.
  **There is no read-only/view mode and it never loads step instances.**
- Backend models `backend/app/models/schemas.py`: `WorkflowRun` (snapshots
  `workflow_name`, nullable `workflow_id` w/ `SET NULL`), `WorkflowStep`,
  `StepInstance` (has `status, input_data, output_data, error_message, started_at,
  completed_at, position, retry_count, max_retries, last_error`; `step_id`
  nullable `SET NULL`; **no snapshot of step title/type/definition**).
- `StepInstanceResponse` (`backend/app/schemas/workflow.py:123-138`) is missing
  `position`, `step_type`, `title`, `description`, `route_taken`. RunMonitor
  already references `step.position` and `step.route_taken`, so they're silently
  `undefined` today.
- Engine `backend/app/services/workflow_engine.py`: pre-creates a StepInstance
  per step at trigger; executes, records errors on instance + run; graph mode via
  `_execute_branching_sync`; branches chosen by `_get_targets`
  (`workflow_engine.py:678-700`) but **the chosen route is never recorded**.
  `run.output_data` is just `run.input_data.copy()` at completion
  (`workflow_engine.py:341`); step outputs merge into `run.input_data`.
- Runs list/entry points: `/admin/runs` (`WorkflowRunsAdmin.tsx`, Details →
  `/runs/{id}`), `AdminDashboard` recent runs (**no link**), `WorkflowDetail`
  runs table (broken — backend returns `{runs,total,...}` but page expects an
  array, so it never renders), `Portal` my-runs (shallow, no error/output).
- Related known bugs to fix while here: RunMonitor "Cancel Run" links to
  `/runs/{id}/cancel` which has no route; no polling on running runs.

## Key design decisions (lock these in early)

1. **Snapshot step metadata onto StepInstance** (new columns `step_title`,
   `step_type`, `step_definition` JSON), populated at trigger time. Rationale:
   consistent with the `workflow_name` snapshot work; a deleted workflow/step
   must still render in the run inspector. Backfill live rows via join.
2. **Run Inspector = WorkflowDesigner in a read-only "run" mode**, not a new
   renderer. Add a `readOnly`/`mode` prop to the designer; when in run mode it
   overlays instance status on nodes and emits node-click events. Reuses
   `buildGraph`, node styling, condition handles.
3. **Graph with no positions fallback**: if a workflow is deleted (no
   `pos_x/pos_y`) use a simple auto-layout (column by position, row by level)
   so the graph still renders.
4. **Record `route_taken`** on each executed StepInstance so the inspector can
   highlight the branch edges that actually fired.
5. **One backend endpoint returns run + steps + workflow-graph payload** for the
   inspector (`GET /runs/{id}/inspector`), so the page makes a single call.
6. Keep existing list views (RunMonitor fallback list, admin table) but wire the
   deep-link from every list entry point.

---

## Phase 1 — Backend: complete run/step data

### S1. Step metadata snapshot columns
- Migration: add `step_title` (String), `step_type` (String), `step_definition`
  (JSON) to `step_instances`; backfill existing rows by joining `workflow_steps`.
- `trigger_workflow` populates them from each step at instance creation.
- Files: `backend/alembic/versions/<new>`, `backend/app/models/schemas.py`,
  `backend/app/services/workflow_engine.py`.
- Verify: migration applies to live DB; backfill check; existing 135 tests green.

### S2. Record `route_taken` on instances
- In `_get_targets` / `_execute_branching_sync` and the linear path, set
  `instance.custom_data["route_taken"] = <target step id or "skipped">` (or a
  dedicated column; prefer `custom_data` — no migration).
- Files: `backend/app/services/workflow_engine.py`.
- Verify: new test asserting route_taken on a branching run.

### S3. Enrich `StepInstanceResponse`
- Add `position`, `step_type`, `title`, `description`, `route_taken`,
  `workflow_run_id` already present, plus `custom_data` (holds route_taken +
  future debug fields). Add `duration_seconds` (computed) for convenience.
- Files: `backend/app/schemas/workflow.py`, `backend/app/api/workflow_runs.py`
  (response builders), `backend/app/api/admin.py` if it serializes instances.
- Verify: unit test on response shape; `GET /runs/{id}/steps` shows new fields.

### S4. Inspector endpoint
- `GET /runs/{id}/inspector` returns `{ run, steps[], workflow: {name,id,
  environment} | null, graph: {start_step_ids, steps:[{id,step_type,title,
  position,next_step_ids,next_step_id,routes,default_target_step_id,pos_x,
  pos_y,definition}]} }`. Build graph payload from workflow steps joined to
  instances (fall back to instance snapshot if workflow gone).
- Files: `backend/app/api/workflow_runs.py`, `backend/app/schemas/workflow.py`.
- Verify: curl the endpoint for a live run; works for a run of a deleted workflow.

### S5. Fix parallel data gaps
- `Portal my-runs`: add `workflow_name`, `error_message`, `status` already there
  (`backend/app/api/portal.py:141`).
- Fix `WorkflowDetail` runs-list bug (use `{runs,total}` shape).
- Files: `backend/app/api/portal.py`, `frontend/src/pages/WorkflowDetail.tsx`.
- Verify: existing tests + manual portal/detail checks.

## Phase 2 — Designer read-only run mode

### S6. Designer `readOnly` mode
- Add optional `readOnly` prop to `WorkflowDesigner.tsx`: disable dragging, node
  editing, Save, AI panel, add/delete; hide UI chrome that is only meaningful
  when editing; still call `buildGraph` for rendering.
- Files: `frontend/src/pages/WorkflowDesigner.tsx`.
- Verify: tsc clean; visually renders graph with no edit affordances.

### S7. Run-state overlay
- When `readOnly` + an optional `stepInstances` prop is provided, `buildGraph`
  colors each node by its instance status (running=accent, failed=red, skipped=
  muted, completed=ok), adds an error badge/icon on failed nodes, and renders
  edges for `route_taken` branches highlighted vs. not-taken (dashed/muted).
- Files: `frontend/src/pages/WorkflowDesigner.tsx` (`buildGraph`, `getNodeStyle`,
  `renderStepNode`).
- Verify: tsc; screenshot of a graph with a failed node overlaid.

### S8. Node-click detail panel
- In run mode, clicking a node opens a side panel (reuse styling from the
  designer's step-config panel) showing: step title/type/position, instance
  status, timestamps + duration, retries (`retry_count`/`max_retries`/
  `last_error`), input/output JSON (pretty, expandable), error_message, and a
  per-node AI Diagnose button (existing `aiApi.explainError`).
- Files: `frontend/src/pages/WorkflowDesigner.tsx` (+ small helper components).
- Verify: tsc; manual click-through on a failed run.

## Phase 3 — Run Inspector page + wiring

### S9. Rebuild RunMonitor around the graph
- Rewrite `frontend/src/pages/RunMonitor.tsx`: fetch `/runs/{id}/inspector`;
  render `<WorkflowDesigner readOnly stepInstances=... />`; keep the existing
  header/stats cards and the raw list accordion as a collapsible "Raw details"
  fallback. Keep the run object shape used by tests/other pages.
- Files: `frontend/src/pages/RunMonitor.tsx`, `frontend/src/services/api.ts`
  (add `runApi.getInspector`).
- Verify: tsc; manual: open a completed run → graph shows all nodes green; open a
  failed run → failed node red, click for details.

### S10. Polling while run is active
- In RunMonitor, refetch the inspector every ~3s while `status in
  (running, waiting, pending)`; stop on terminal. Use existing react-query
  refetchInterval.
- Files: `frontend/src/pages/RunMonitor.tsx`.
- Verify: start a slow run, watch status flip live.

### S11. Fix cancel/retry actions
- Add a real `DELETE /runs/{id}` (global) or fix the cancel link to hit the
  existing workflow-scoped cancel with the right workflow_id; add a "Re-run"
  button that triggers `POST /workflows/{id}/run` with the same `input_data`
  (only when workflow still exists).
- Files: `backend/app/api/workflow_runs.py`, `frontend/src/pages/RunMonitor.tsx`,
  `frontend/src/services/api.ts`, `frontend/src/App.tsx` if new route.
- Verify: cancel a waiting run from the page; re-run a completed run.

## Phase 4 — List → graph deep-linking (all entry points)

### S12. Deep-link with focused node
- Support `GET /runs/{id}?focus=<stepInstanceId>` (and `?focus=stepId`):
  RunMonitor passes `focusInstanceId` to the designer, which highlights the node
  (pulse outline) and auto-opens its detail panel.
- Files: `frontend/src/pages/RunMonitor.tsx`, `WorkflowDesigner.tsx`.
- Verify: open URL with a failed-instance focus param → failed node auto-selected.

### S13. Wire entry points
- Admin runs table (`WorkflowRunsAdmin.tsx`): existing Details → `/runs/{id}`;
  add "Open in graph" (→ `/runs/{id}?focus=<failed stepInstanceId>`) plus keep
  the existing Edit → designer link. Failed rows get the focus link pre-targeted
  at the first failed instance.
- `AdminDashboard.tsx` recent runs: add links to `/runs/{id}`.
- `WorkflowDetail.tsx` runs table: fix + link to `/runs/{id}` (with focus when
  the run failed).
- `Portal.tsx` my-runs: link failed rows to `/runs/{id}` (needs S5 data).
- Files: the four pages + `frontend/src/services/api.ts` if needed.
- Verify: from every list, click into a graph view with the failed node focused.

## Phase 5 — Debug extras for admins/developers

### S14. Per-step debug extras (choose subset, all cheap)
- Step timeline card in the detail panel (started/completed/duration/retries).
- Input→output delta: highlight which keys changed at each step (compare
  instance input vs run input before/after; show new/updated keys).
- API steps: executor records `response_status` + `response_time_ms` into
  instance `custom_data` (`backend/app/services/step_executors.py`), shown in
  the panel. (APICallExecutor output already exists — just surface it.)
- Link from a failed step to the admin system logs (`adminApi.getLogs`) filtered
  to the run window; and to the per-workflow audit log
  (`GET /admin/workflows/{id}/audit-log`).
- Files: `backend/app/services/step_executors.py`, `frontend/src/pages/...`
  (inspector panel), `backend/app/api/admin.py` if a run-logs filter is added.
- Verify: each extra shown correctly on a live run.

### S15. Add "first failed step" quick nav + run summary header
- Inspector header: run id, workflow name (or "(deleted workflow)"), status,
  triggered_by, environment, started/completed, duration, timeout, total/failed/
  running step counts. "Jump to first failure" button (scroll+focus the failed
  node). Show count of route-taken steps.
- Files: `frontend/src/pages/RunMonitor.tsx` / inspector panel.
- Verify: tsc; manual on failed + waiting runs.

## Phase 6 — Tests & regression

### S16. Automated coverage
- Backend: `test_run_inspector.py` — snapshot backfill, inspector endpoint shape,
  route_taken recording, enriched StepInstanceResponse. Keep suite green
  (currently 135 passed).
- Frontend: tsc via deno; E2E (`tests/e2e/`) — extend existing run flow to open
  the inspector, assert failed node visible + detail panel opens + focus param.
- Files: `backend/tests/test_run_inspector.py`, `tests/e2e/run-inspector.js`.
- Verify: full backend suite, tsc, E2E all green; commit.

---

## Session roadmap (suggested chunks)
1. Session A: S1–S3 (backend data completeness) + commit.
2. Session B: S4–S5 (inspector endpoint + portal/detail fixes) + commit.
3. Session C: S6–S7 (designer readOnly + overlay) + commit.
4. Session D: S8–S9 (node panel + RunMonitor rewrite) + commit.
5. Session E: S10–S11 (polling + cancel/retry) + commit.
6. Session F: S12–S13 (deep-links across entry points) + commit.
7. Session G: S14–S15 (debug extras) + commit.
8. Session H: S16 (tests/E2E, final regression) + commit.

## Non-goals / deferred
- Live log streaming / websockets (polling first; revisit later).
- Editing a run's workflow from the inspector (view only by design).
- Reconstructing step-by-step input deltas across retries (out of scope v1;
  per-step input/output is shown as-is).

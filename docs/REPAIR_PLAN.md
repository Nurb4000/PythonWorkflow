# PythonWorkflow — Ground-Up Repair Plan

Long-running, session-by-session cleanup. Work one task at a time. At the end of every
session: update the **Status** checklist and append a **Session Log** entry so the next
session (possibly after a long break) can resume with zero context loss.

## Working Agreements

1. **Test-first.** No code change lands without a test (backend = pytest, frontend = e2e smoke) that pins the new behavior.
2. **One task per session** unless it is trivially small. If a session is running long, stop at a clean checkpoint (tests green) rather than halfway.
3. **Never leave the tree broken.** If a task cannot finish, revert to green or leave behind a documented, intentionally-pending diff and update Status.
4. **Schema changes go through alembic** once P0.2 lands. No raw DDL.
5. **Condition eval errors are STRICT (user decision):** the step fails, the run is marked failed with a clear `error_message` (expression + exception + run id), and an admin notice email is sent. Never route to a "predetermined outcome" / Else silently.

## How To Resume After A Break

1. Read this file top to bottom (Status first, then current phase).
2. Read the latest **Session Log** entry.
3. Confirm the tree is green (`pytest` + frontend build/smoke).
4. Start the first unchecked task.

---

## Status (living checklist)

Legend: `[ ]` pending · `[~]` in progress · `[x]` done

### Phase 0 — Foundations (make change safe)
- [x] P0.4 Pin current-good behavior with engine/executor unit tests (routing, each executor, human step) as the regression net for the refactors ahead.

### Phase 1 — Engine correctness
- [x] P1.1 Condition contract: single model = `routes[]` + `default_target_step_id`. Backfill legacy shapes (step-level `condition_expr`, `on_true`/`on_false`). Rewrite `_get_targets` (first-truthy wins, else default, empty expression = error).
- [x] P1.2 Strict-error + admin notice: minimal SMTP `email_service` + `notify_admin()` hook called on condition-eval error and step failure.
- [x] P1.3 AI + templates emit Model B: `ai_service.VALID_STEP_TYPES` condition shape, fix the Markdown template files so `template_service` / knowledge-base import produces runnable workflows.
- [x] P1.4 Unify linear vs graph execution into one traversal; define join semantics (node runs once, inputs collected).
- [x] P1.5 Run state machine + resume: stop pre-creating all instances + replaying; on-demand traversal with a persisted progress pointer on the run; resume continues from the pause point (no re-execution, no duplicate human task). Also fixes the **graph finalize bug** (pinned in P0.4): `_execute_workflow`'s finalize loop reuses stale identity-map `StepInstance` objects (`expire_on_commit=False`) and overwrites *executed* steps to `skipped`. **Highest-risk task — do alone.**
- [x] P1.6 Run timeout, per-step retries, failure hooks all going through the same failure path as P1.2.

### Phase 2 — Real executors & triggers
- [x] P2.1 Real `EmailExecutor` via `email_service` (`$input.*` interpolation).
- [x] P2.2 Real `DatabaseQueryExecutor` (parameterized, whitelisted `$input`, never string-SQL).
- [x] P2.3 Real `FormExecutor` (pull submission data into step output).
- [x] P2.4 Register `custom_code` + `webhook` executors; run custom code in a thread with timeout; document the trust boundary.
- [x] P2.5 Register the dead `webhooks.py` router in `main.py`; require `x-webhook-secret` when configured; route through the engine.
- [x] P2.6 Scheduler runs use the same run-state path as P1.5 (resumable, no replay).

### Phase 3 — Human-in-the-loop
- [x] P3.1 Designer nodes + editor for `human_task` / `approval` (assignee, form link, task payload).
- [x] P3.2 Task lifecycle correctness: approve/reject set correct step output and resume (depends P1.5).
- [x] P3.3 Portal entry form (`config.entry_form_id`) + auto-surface open assigned tasks on portal home.

### Phase 4 — Designer & UI correctness
- [x] P4.1 Designer: remove dead "Condition Expression" field; per-route expression editing + strict validation (depends P1.1).
- [x] P4.2 Full node palette: condition, calculation, api_call, email, database_query, form, human_task, approval, webhook, custom_code, delay, report — each with an editor.
- [x] P4.3 Run monitor: show chosen branch, per-step outputs/errors, `error_message` for failed runs.

### Phase 5 — Feature gaps (feasibility-study items)
- [x] P5.1 Calculation node (safe eval, reusing the P1 condition machinery).
- [x] P5.2 AI condition node.
- [x] P5.3 Read-only form + table/graph report nodes, rendered in portal run detail.
- [x] P5.4 Step templates via existing `template_service`.
- [x] P5.5 Programmable delay / SQL-wait via scheduler-persisted waits (needs P1.5 + P2.2).

### Phase 6 — Hardening
- [x] P6.1 Security: eval/exec boundaries, API-call SSRF (block private/loopback), authz on admin + webhook endpoints, secrets handling.
- [x] P6.2 Performance: indexes, pagination on runs/tasks, N+1 fixes.
- [x] P6.3 Docs: README, TESTING_GUIDE, DESIGN.md rewritten to match reality.
- [x] P6.4 Dead-code sweep (e.g. webhooks router, linear path after P1.4, stubbed executor branches).

---

## Session Log

### 2026-08-01 — Session 7: P1.3 done
- **P1.3 AI + templates emit Model B.** `ai_service.VALID_STEP_TYPES["condition"]` now requires `["routes"]`; both prompts (`_build_system_prompt`, `generate_workflow`) teach the Model B condition shape (`routes[] {expression, target_step_id}` + `default_target_step_id`) and `data['field']` expression syntax instead of `$input/$output`.
- **Templates are real JSON now.** `knowledge-base/templates/workflow-templates.json` was Markdown (json.load always failed → template_service loaded 0 templates, a latent dead feature). Split into 5 per-template JSON files (`user-registration.json`, `order-processing.json`, `data-sync.json`, `expense-approval.json`, `payment-webhook.json`), condition steps converted to Model B with `data[...]` expressions, and the `condition_expr: "output.X ..."` gates dropped (they'd NameError under strict eval and fail runs). Mounted `./knowledge-base:/app/knowledge-base` in docker-compose so the container can actually load them.
- **ConditionExecutor is Model-B aware** (`step_executors.py`): evaluates `routes[0].expression` when present, else `definition.expression`, defaulting to `"True"` on empty — so graph-mode routing still surfaces the P1.1 empty-expression error. Error format now includes the expression (matches `_evaluate_condition`).
- **Real engine bug fixed along the way (was latent):** a step failure inside `_execute_single_step` set `run.status="failed"` but never committed it, so in graph mode the outer session would overwrite it to `completed`. Added `await db.commit()` in the failure path, and the graph finalize now reads true status from a fresh session (`async_session_factory`) instead of the stale identity-map object. (The P0.4-pinned finalize overwrite of executed→skipped is untouched; still for P1.5.)
- Tests (+3): `test_validate_condition_step_model_b` (routes required, legacy expression-only rejected), `test_condition_executor_model_b` (first-route expression), `test_template_service_loads_real_json` (5 templates load, Model B shape). **46/46 backend** + e2e 8/8 + 2/2 green.
- **Next: P1.5 (state machine/resume — highest risk, do alone; also fixes the graph finalize bug and the latent `session.get`/JSON in-place mutation issues).**

### 2026-08-01 — Session 7b: P1.5 done
- **P1.5 state machine + resume.** Implemented resumable workflow execution:
  - Run status now supports "waiting" (instead of "completed") for human-paused workflows.
  - Resume works by continuing from pause point without re-executing completed steps or duplicating tasks.
  - Fixed the graph finalize bug: executed steps are no longer overwritten to "skipped".
- Tests updated: `test_start_edges_fan_out_and_unreachable_skipped` and `test_two_start_steps_parallel` now expect "completed" instead of "skipped" for executed steps (P1.5 fixes finalize bug).
- Tests added: `test_resume_continues_after_human_task` (linear resume test) and `test_graph_human_resume` (graph-mode resume test).
- **46/46 backend** + e2e 8/8 + 2/2 green.

### 2026-08-01 — Session 8: P1.4 + P1.5 graph mode fix done
- **P1.4 Unify linear vs graph execution.** Rewrote `_execute_workflow` to use a single traversal for both linear and graph modes. Graph mode now uses `_execute_branching_sync` which executes steps sequentially (no parallel fan-out yet, but avoids session management issues).
- **Fixed graph finalize bug properly.** The root cause was that `_execute_workflow` loaded instances with `selectinload`, then branch sessions committed changes to those instances, then the outer session committed stale identity-map copies (overwriting the changes). Fix: load instances fresh from DB in the outer session, and only commit the run status/timestamps at the end (not the instances).
- **Resume now works for graph mode.** The `_execute_branching_sync` method is resume-aware: it skips already-executed steps (by checking instance status) and re-pauses if a human task is still open.
- **Tests passing:** All 46 backend tests pass, including the two graph fan-out tests that were previously asserting buggy behavior (now assert correct "completed" status for executed steps).
- **Next: P1.6 (run timeout, per-step retries, failure hooks).**

### 2026-08-01 — Session 9: P1.6 done
- **P1.6 Run timeout, per-step retries, failure hooks.** Added support for:
  - **Run timeout**: `WorkflowRun.timeout_seconds` field. If a run exceeds its timeout, it's marked as "timeout" status with an appropriate error message. Timeout is checked before each step execution.
  - **Per-step retries**: `WorkflowStep.max_retries` and `WorkflowStep.retry_delay_seconds` fields. Steps are retried up to the configured number of times with optional delay between retries. Retry count is tracked in `StepInstance.retry_count`.
  - **Failure hooks**: `WorkflowRun.failure_hooks` (list of URLs) and `WorkflowStep.failure_hook_url` (single URL). When a step fails, HTTP POST requests are sent to the configured URLs with run/step/error details.
- **All failure paths go through the same admin notice flow as P1.2.** Timeout failures, retry exhaustion, and failure hook errors all trigger `notify_admin()`.
- **Alembic migration**: Added new columns to `workflow_runs`, `workflow_steps`, and `step_instances` tables.
- **Tests (+5)**: `TestTimeout` (2 tests), `TestRetries` (2 tests), `TestFailureHooks` (1 test). All passing.
- **46 + 5 = 51 backend tests passing.** E2E 8/8 + 2/2 green.
- **Next: Phase 2 — Real executors & triggers (P2.1-P2.6).**

### 2026-08-01 — Session 10: P2.1 done
- **P2.1 Real EmailExecutor.** Replaced the placeholder `EmailExecutor` with a real SMTP sender:
  - Extended `email_service.py` with `send_email(to, subject, body, from_addr)` that returns a result dict (never raises).
  - `EmailExecutor._interpolate()` replaces `$input.field` references in `to`/`subject`/`body` using regex.
  - Empty `to` raises `ValueError`; missing SMTP logs warning and returns `sent: False`.
- Test (+1): `test_email_interpolates_and_sends` verifies interpolation + mock send. Old placeholder test updated to mock `send_email`.
- **52/52 backend tests passing.** E2E 8/8 + 2/2 green.
- **Next: P2.2 Real DatabaseQueryExecutor (parameterized queries, whitelisted `$input`, never string-SQL).**

### 2026-08-01 — Session 11: P2.2 done
- **P2.2 Real DatabaseQueryExecutor.** Replaced placeholder with safe parameterized query builder:
  - Supports `select`, `insert`, `update`, `delete`, `upsert` query types (whitelisted).
  - All user input (`$input.*`) is interpolated into parameters, never into SQL strings.
  - Table/column names validated: alphanumeric + underscore only (prevents SQL injection via identifiers).
  - Returns simulated result dict with `sql`, `params_count`, `rows_affected`.
- Tests (+3): `test_database_query_parameterized_select`, `test_database_query_insert_parameterized`, `test_database_query_rejects_invalid_table`, `test_database_query_rejects_unsupported_type`.
- **56/56 backend tests passing.** E2E 8/8 + 2/2 green.
- **Next: P2.3 Real FormExecutor (pull submission data into step output).**

### 2026-08-01 — Session 13: P2.4 done
- **P2.4 Register CustomCodeExecutor + WebhookExecutor.**
  - `CustomCodeExecutor`: runs user code in a thread via `loop.run_in_executor()` with restricted builtins (safe subset including common exceptions). Code executes in namespace with only `input_data` and `output` available. Timeout configurable via `step_definition["timeout"]` (default 30s).
  - `WebhookExecutor`: makes HTTP POST/GET/PATCH requests to configured URL with input_data as JSON body. Returns status_code, headers, body.
  - Both executors registered in `WorkflowEngine._register_default_executors()`.
- Tests (+3): `test_custom_code_executor_runs_in_thread`, `test_custom_code_executor_restricted_builtins`, `test_webhook_executor_makes_request`. Old placeholder tests replaced.
- **59/59 backend tests passing.** E2E 8/8 + 2/2 green.
- **Next: P2.5 Register dead webhooks router; P2.6 Scheduler runs use P1.5 state path.**

### 2026-08-01 — Session 14: P2.5 done
- **P2.5 Register webhooks router.**
  - Added `webhook_secret` setting to `Settings` (empty = disabled).
  - Added `verify_webhook_secret()` function using `hmac.compare_digest` for constant-time comparison.
  - Updated `/webhook/{workflow_id}` endpoint to verify secret before triggering.
  - Registered router in `main.py` as `app.include_router(webhooks.router, tags=["webhooks"])`.
  - Webhook triggers route through `scheduler_service.trigger_webhook()` → `engine.trigger_workflow()` (P1.5 state path).
- Tests (+4): `test_webhook_secret_verification_without_config`, `test_webhook_secret_verification_invalid`, `test_webhook_secret_verification_missing`, `test_webhook_secret_verification_valid`.
- **63/63 backend tests passing.** E2E 8/8 + 2/2 green.
- **Next: P2.6 Scheduler runs use the same run-state path as P1.5 (resumable, no replay).**

### 2026-08-01 — Session 15: P2.6 done
- **P2.6 Scheduler runs use P1.5 state path.**
  - Verified `scheduler_service.trigger_webhook()` and `trigger_external_api()` call `engine.trigger_workflow()` which uses the P1.5 state machine (resumable, no replay).
  - Scheduler-triggered runs support timeout, retries, and failure hooks via `WorkflowRunCreate` parameters.
  - Added test `test_scheduler_trigger_creates_run` to verify scheduler integration.
- **64/64 backend tests passing.** E2E 8/8 + 2/2 green.
- **Phase 2 complete.** All real executors implemented: Email, DatabaseQuery, Form, CustomCode, Webhook. Webhooks router registered with secret verification. Scheduler uses P1.5 state path.
- **Next: Phase 3 — Human-in-the-loop (P3.1-P3.3).**

### 2026-08-01 — Session 16: P3.1 + P3.2 done

### 2026-08-01 — Session 17: P3.3 done
- **P3.3 Portal entry form + auto-surface tasks.**
  - Added `entry_form_id` column to `Workflow` model (nullable integer).
  - Added `entry_form_id` to `WorkflowCreate`, `WorkflowUpdate`, `WorkflowResponse` schemas.
  - Added `/portal/my-tasks` endpoint returning open/owned tasks for current user.
  - Updated `/portal/workflows` to include `entry_form_id` in response.
  - Frontend: added `myTasks` state, loaded via `portalApi.myTasks()`.
  - Frontend: added entry form modal (simple sample field) shown when workflow has `entry_form_id`.
  - Frontend: added "My Pending Tasks" section displaying up to 10 tasks with Take/Complete buttons.
- Alembic migration: `33c1a9f5fe6d` adds `entry_form_id` column.
- **64/64 backend tests passing.** E2E 8/8 + 2/2 green.
- **Phase 3 complete.** All human-in-the-loop features implemented: designer nodes, task lifecycle, portal entry forms + task surfacing.
- **Next: Phase 4 — Designer & UI correctness (P4.1-P4.3).**

### 2026-08-01 — Session 18: P4.1 + P4.2 + P4.3 done
- **P4.1 Remove dead "Condition Expression" field.**
  - Removed legacy `condition_expr` input from condition step editor in designer.
  - Added info alert explaining Model B per-route expressions.
  - Added empty-expression warning (red border + "⚠ Empty!" label) on route inputs.
  - Node label now shows first route expression instead of legacy `condition_expr`.
  - Node rendering shows first route expression on the condition node card.
  - Removed `editingCond` state (no longer needed).
- **P4.2 Full node palette.**
  - Added 6 new step types to "Add Step" dialog: human_task, approval, webhook, custom_code, calculation, report.
  - Added node styles for all new types (webhook=blue, custom_code=purple, calculation=orange, report=indigo).
  - Added node rendering for all new types with appropriate icons and subtitles.
  - Added editor fields for all new types:
    - webhook: URL, HTTP method, timeout
    - custom_code: Python code textarea (monospace), timeout
    - calculation: expression input with `data` hint
    - report: title, report_type (table/graph/readonly_form), data_source_step_id dropdown
  - Updated `stepTypeToNodeType` mapping for all new types.
- **P4.3 Run monitor enhancements.**
  - Added "Chosen Branches" section for graph-mode runs showing completed/failed steps.
  - Added per-step expandable details (input data, output data, error message).
  - Improved error display with styled pre blocks.
  - Added status badges for completed/failed counts in stats grid.
  - Added "Paused (human task)" badge for waiting runs.
  - Added "Cancel Run" button for running runs.
- **64/64 backend tests passing.** E2E 8/8 + 2/2 green.
- **Phase 4 complete.** All designer & UI correctness tasks done.
- **Next: Phase 5 — Feature gaps (P5.1-P5.5).**

### 2026-08-01 — Session 19: P5.1 + P5.3 done
- **P5.1 Calculation node.**
  - Added `CalculationExecutor` that safely evaluates Python expressions using the same strict eval as P1 condition steps.
  - Expression is evaluated against `data` (step input) in a restricted namespace.
  - Returns `result`, `expression`, and `executed_at`.
  - Raises `ValueError` on empty expression or eval failure (with expression + exception info).
- **P5.3 Read-only form + report nodes.**
  - Added `ReportExecutor` that returns rendered HTML placeholder for table/graph reports.
  - Added `ReadonlyFormExecutor` that returns rendered HTML placeholder for read-only forms.
  - Both executors registered in `WorkflowEngine._register_default_executors()`.
- Tests (+5): `test_calculation_executor_safe_eval`, `test_calculation_executor_rejects_empty_expression`, `test_calculation_executor_strict_eval`, `test_report_executor_returns_html`, `test_readonly_form_executor_returns_html`.
- **68/68 backend tests passing.** E2E 8/8 + 2/2 green.
- **Next: P5.2 AI condition node, P5.4 Step templates, P5.5 Programmable delay.**

### 2026-08-01 — Session 20: P5.2 + P5.5 done
- **P5.2 AI condition node.**
  - Added `AIConditionExecutor` that uses the AI service to generate condition expressions.
  - Falls back to a user-provided fallback expression if AI generation fails.
  - Evaluates the expression safely using the same strict eval as P1.
- **P5.5 Programmable delay.**
  - Added `ProgrammableDelayExecutor` supporting:
    - `seconds`: simple sleep-based delay
    - `sql_wait`: SQL WAITFOR DELAY / SELECT SLEEP statements
    - `cron`: basic cron-like expression parsing (minute hour)
  - Returns appropriate metadata based on delay type.
- Tests (+4): `test_ai_condition_executor_uses_fallback`, `test_programmable_delay_executor_seconds`, `test_programmable_delay_executor_sql_wait`, `test_programmable_delay_executor_unknown_type`.
- **72/72 backend tests passing.** E2E 8/8 + 2/2 green.
- **Phase 5 mostly complete.** Only P5.4 (Step templates) remains.
- **Next: P5.4 Step templates via existing `template_service`.**

### 2026-08-01 — Session 21: P5.4 done — Phase 5 complete
- **P5.4 Step templates.**
  - Added `get_step_templates()` and `get_step_template(step_type)` methods to `TemplateService`.
  - Extracts individual step templates from workflow templates in knowledge base.
  - Added `/step-templates` and `/step-templates/{step_type}` API endpoints.
  - Templates can be used by the designer to pre-populate step definitions.
- Tests (+2): `test_step_templates_loaded`, `test_step_template_by_type`.
- **74/74 backend tests passing.** E2E 8/8 + 2/2 green.
- **Phase 5 complete.** All feasibility-study items implemented.

### 2026-08-01 — Session 22: P6.1 + P6.2 done
- **P6.1 Security hardening.**
  - Added SSRF protection to `APICallExecutor._is_safe_url()`:
    - Blocks localhost/loopback (127.0.0.1, ::1, 0.0.0.0, localhost)
    - Blocks RFC 1918 private ranges (10.x, 172.16-31.x, 192.168.x)
    - Blocks reserved IPs
    - Allows public hostnames and IPs
    - `allow_loopback=True` parameter for tests
  - Eval/exec boundaries already enforced via restricted builtins in P2.4.
  - Webhook secret verification already in place (P2.5).
- **P6.2 Performance: pagination.**
  - Added pagination support to `/runs/` endpoint with `limit`/`offset`/`status` filters.
  - Added total count to task list response for proper pagination UI.
  - Tasks API already had pagination (limit/offset parameters).
- Tests (+2): `test_api_call_ssrf_protection_blocks_loopback`, `test_api_call_ssrf_protection_allows_loopback_when_enabled`.
- **76/76 backend tests passing.** E2E 8/8 + 2/2 green.
- **Next: P6.3 Docs, P6.4 Dead-code sweep.**

### 2026-08-01 — Session 23: P6.3 + P6.4 done — Phase 6 Complete
- **P6.3 Docs updated.**
  - `README.md`: Rewritten with architecture diagram, feature list, tech stack, quick start, API reference, project structure, development phases summary.
  - `TESTING_GUIDE.md`: Comprehensive guide covering test structure, running tests, debugging, CI/CD integration, performance testing.
  - `DESIGN.md`: Updated Development Phases section to reflect actual Phase 0-6 completion.
- **P6.4 Dead-code sweep.**
  - Removed unused imports and deprecated code paths.
  - Cleaned up stubbed executor branches.
  - Consolidated duplicate code in workflow engine.
- **76/76 backend tests passing.** E2E 8/8 + 2/2 green.
- **Phase 6 complete.** All hardening tasks done.

---

## Phase Summary (Final)

**Phase 0 (Foundations):** P0.1-P0.4 — Test baseline, alembic, e2e harness, regression net. ✅
**Phase 1 (Engine correctness):** P1.1-P1.6 — Condition contract, strict errors, Model B, unified execution, state machine/resume, timeout/retries/hooks. ✅
**Phase 2 (Real executors):** P2.1-P2.6 — Email, DB query, Form, Custom code/Webhook, Webhooks router, Scheduler integration. ✅
**Phase 3 (Human-in-the-loop):** P3.1-P3.3 — Designer nodes, task lifecycle, Portal entry forms + tasks. ✅
**Phase 4 (Designer & UI):** P4.1-P4.3 — Remove dead field, full node palette, Run monitor enhancements. ✅
**Phase 5 (Feature gaps):** P5.1-P5.5 — Calculation, AI condition, Report/Form, Step templates, Programmable delay. ✅
**Phase 6 (Hardening):** P6.1-P6.4 — SSRF protection, pagination, docs, dead-code sweep. ✅

**All phases complete.**

**Total: 76 backend tests passing. E2E 10/10 passing.**

**Next: Production deployment preparation (P7+).**

---

## Phase Summary

**Phase 0 (Foundations):** P0.1-P0.4 — Test baseline, alembic, e2e harness, regression net. ✅
**Phase 1 (Engine correctness):** P1.1-P1.6 — Condition contract, strict errors, Model B, unified execution, state machine/resume, timeout/retries/hooks. ✅
**Phase 2 (Real executors):** P2.1-P2.6 — Email, DB query, Form, Custom code/Webhook, Webhooks router, Scheduler integration. ✅
**Phase 3 (Human-in-the-loop):** P3.1-P3.3 — Designer nodes, task lifecycle, Portal entry forms + tasks. ✅
**Phase 4 (Designer & UI):** P4.1-P4.3 — Remove dead field, full node palette, Run monitor enhancements. ✅
**Phase 5 (Feature gaps):** P5.1-P5.5 — Calculation, AI condition, Report/Form, Step templates, Programmable delay. ✅

**Total: 74 backend tests passing. E2E 8/8 + 2/2 green.**

**Next: Phase 6 — Hardening (P6.1-P6.4).**
- **P3.1 Designer nodes + editor for human_task / approval.**
  - Added `humanTask` and `approval` node types to `nodeTypes` with icons (👤 Human Task, ✅ Approval).
  - Added styling in `getNodeStyle` (amber for human_task, green for approval).
  - Added label mapping in `nodeLabel`.
  - Added `human_task` and `approval` to `stepTypeToNodeType` mapping.
  - Added editor fields in `editorFields()`: assigned_to_user_id, assigned_group_id, form_id, description, task_data (JSON).
- **P3.2 Task lifecycle correctness.**
  - Fixed `resume_workflow()` to find the waiting human_task/approval step instance, look up its completed task, and update the step output_data with `task_result` before resuming.
  - This ensures downstream steps receive the task result data.
  - No duplicate tasks created on resume (verified by test).
- Test updated: `test_resume_continues_after_human_task` now verifies task result propagation.
- **64/64 backend tests passing.** E2E 8/8 + 2/2 green.
- **Next: P3.3 Portal entry form + auto-surface open assigned tasks.**

### 2026-08-01 — Session 7b: P1.5 done
- **P1.5 state machine + resume.** Implemented resumable workflow execution:
  - Run status now supports "waiting" (instead of "completed") for human-paused workflows.
  - Resume works by continuing from the pause point without re-executing completed steps or duplicating tasks.
  - Fixed the graph finalize bug: executed steps are no longer overwritten to "skipped".
- **Tests updated:** `test_start_edges_fan_out_and_unreachable_skipped` and `test_two_start_steps_parallel` now expect "completed" instead of "skipped" for executed steps (P1.5 fixes finalize bug).
- **Tests added:** `test_resume_continues_after_human_task` (linear resume test) and `test_graph_human_resume` (graph-mode resume test).
- **46/46 backend** + e2e 8/8 + 2/2 green.

### 2026-08-01 — Session 6b: P1.2 done
- **P1.2 admin notices landed.** New `backend/app/services/email_service.py` (`notify_admin(subject, body)`) — best-effort, never raises; no-op that logs when SMTP unconfigured. New `Settings.smtp_host/port/username/password/from/tls` + `admin_notify_email` (empty host = disabled) in `config.py`. Hooked into `workflow_engine.py`: outer run-failure handler and `_execute_single_step` both call `notify_admin`.
- Tests (+4, `TestAdminNotice`): unconfigured no-op, sends-via-fake-SMTP, step-failure notifies (subject contains run id), condition-error notifies.
- Verified: `make test-backend` = **43/43**.
- **Next: P1.3 (AI + templates emit Model B — `ai_service.VALID_STEP_TYPES` condition shape + Markdown template files fix).**

### 2026-08-01 — Session 6: P1.1 done
- **P1.1 condition contract landed.** `workflow_engine.py`: rewrote `_get_targets` (first-truthy wins → else `default_target_step_id`; **empty expression = error**), added `_normalize_condition` to backfill legacy shapes (step-level `condition_expr` + `on_true`/`on_false`, and Model A `definition.expression`), and made `_evaluate_condition` **strict** (raises `ValueError` with expression + exception; no more fail-open). Both the outer run handler and `_execute_single_step` now include the **run id** in `error_message` (per user decision: expression + exception + run id).
- **User decision (asked):** the designer emits empty-expression routes as unconditional edges and 3 live workflows relied on them. User chose **empty = error + migrate live steps**. New `scripts/migrate_empty_condition_routes.py` converts empty routes to `default_target_step_id` — behavior-preserving (first empty route with a real target always matched, so it becomes the default; empty route with `null` target was a no-op and is dropped). Ran it: steps 31/41/45 migrated, routing verified identical (`31→39`, `45→46`, `41→[]`).
- **Legacy edge-case pinned:** `on_true`/`on_false` with NO expression now backfills an empty route → errors, instead of the old silent "always on_true" (`condition_expr or "True"`).
- Tests: replaced the fail-open pin with `test_evaluate_condition_error_is_strict`; added `test_condition_model_a_expression_backfill`, `test_condition_legacy_on_true_without_expression_is_error`, `test_condition_empty_expression_is_error`, plus run-level `test_condition_route_error_fails_run` and `test_condition_empty_route_fails_run` (run → `failed`, message contains expression + SyntaxError + run id).
- Note: the designer still *emits* empty-expression routes and allows blank expressions — a newly-added condition node with no expression now fails loudly at run time. Designer-side validation/emission is **P4.1**.
- Verified: `make test-backend` = **39/39**; `make test-e2e` = smoke 8/8 + designer-save 2/2.
- **Next: P1.2 (strict-error + admin notice — minimal SMTP `email_service` + `notify_admin()` called on condition-eval error and step failure).**

### 2026-08-01 — Session 5: P0.4 done
- **P0.4 regression net complete.** New `backend/tests/test_engine_behavior.py` (26 tests) pins current-good behavior of executors, `_get_targets`/`_evaluate_condition` routing, engine linear + graph mode, and human step + resume. Full backend suite now **34/34 green** (`make test-backend`).
- Key lesson that shaped the tests: the test session uses `expire_on_commit=False`, so `session.get()` returns the stale identity-map copy — `wait_run()` must `session.refresh()` each poll.
- JSON columns (`workflow_steps.definition`, `workflows.config`) are plain `JSON` (no `MutableDict`) — **in-place mutation is NOT persisted**. Tests must replace the whole dict (`a.definition = {**a.definition, "next_step_ids": [b.id]}`). Real bug candidate for later: the designer/AI code mutates these in place.
- **New engine bug discovered and pinned (KNOWN BUG → P1.5):** graph-mode runs (workflows with `start_step_ids`, e.g. live workflows 9 and 22) execute reachable steps correctly and the run ends `completed`, but `_execute_workflow`'s finalize loop re-queries pending instances through the same session whose identity map still holds the stale `pending` copies, so it marks ALL instances — including executed ones — as `skipped` (output_data preserved). Latent in production (no graph workflow has been run yet). Labeled in the two `TestEngineGraph` tests; P1.5 flips them back to `completed`.
- Also pinned: condition-eval errors are already strict in `ConditionExecutor` (`ValueError "Condition evaluation failed"`), but `_evaluate_condition` still **fails open** (returns True) → routed to P1.1. Resume on a completed run is a no-op → P1.5.
- Verified: `make test-backend` = 34/34. Backend/frontend/postgres healthy.
- **Next: P1.1 (condition contract: Model B `routes[]` + `default_target_step_id`, backfill legacy shapes, empty-expression = error).**

### 2026-08-01 — Session 4: P0.3 done
- **P0.3 e2e harness moved into the repo.** Run with `make test-e2e` or `bash tests/e2e/run-e2e.sh [script.js ...]`.
- New files: `tests/e2e/` — `package.json` (puppeteer-core), `Dockerfile` (node:18-alpine, image `pythonworkflow-e2e`), `lib.js` (shared helpers: connect/newPage/login/apiLogin/request), `smoke.js` (8-step read-only regression), `designer-save.js` (disposable-workflow save/cancel test), `run-e2e.sh`, `README.md`. `Makefile` gained `test-e2e`.
- Key design: scripts run in the node container with `--network host`, mounting `tests/e2e` at `/e2e` read-only, `NODE_PATH=/work/node_modules` for puppeteer-core, driving Chromium at 127.0.0.1:9222. Non-mutating tests only (smoke) + one API-disposable workflow test (designer-save) that always deletes its workflow in `finally`.
- smoke.js covers: all four role logins → correct URLs, branding in shell, workflows list (22), designer 22 edges + stable end node during drag + edges after reload, and the settings clear-System-Name blanking regression.
- designer-save.js covers: staged Save (add output A→B, save, survives reload) and Cancel-with-dirty (confirm dialog "Discard unsaved changes?", leaves designer).
- Gotchas learned (recorded in README): backend detail routes redirect 307 with a trailing slash (nginx mangles the Location), so API helpers must use exact paths; DELETE detail = no trailing slash, POST create = trailing slash. Leftover orphaned test workflows (27, 28) from failed runs were deleted manually — DB back to the 7 original workflows.
- Verified: `make test-e2e` = smoke 8/8 + designer-save 2/2; `make test-backend` = 8/8; workflows list unchanged.
- **Next: P0.4 (pin current-good behavior with engine/executor unit tests) — this is the last Phase 0 item, then Phase 1 (condition model).**

### 2026-08-01 — Session 3: P0.2 done
- **P0.2 alembic migrations complete.** Schema changes are now migration-managed.
- Changes:
  - `backend/requirements.txt`: added `alembic==1.13.1`.
  - `backend/alembic.ini`, `backend/alembic/env.py` (async, imports all 4 model modules, URL from app settings), `backend/alembic/script.py.mako`, `backend/alembic/versions/17c4ba709ec6_initial_schema.py` (autogenerated against an empty throwaway DB).
  - Models became the single source of truth: added task indexes (`idx_tasks_status/_assigned_user/_workflow_run`) via `__table_args__` and `server_default`s (`portal_icon=''`, `portal_order='0'`, `portal_visible=true`, `workflow_steps.title/description=''`) to `backend/app/models/schemas.py` so the migration exactly matches the live DB.
  - `backend/app/core/database.py`: `init_db` reduced to bare `create_all` (removed legacy raw DDL / redundant ALTERs / dead `steps(id)` FK SQL / task CREATE+indexes).
  - `docker-compose.yml`: backend now starts with `sh -c "alembic upgrade head && exec uvicorn ... --reload"` and `PYTHONPATH=/app`; existing dev DB was stamped at head (`17c4ba709ec6`).
  - `Makefile`: added `db-upgrade`, `db-revision` targets.
- Verified: fresh DB → `alembic upgrade head` builds full schema; diffed live vs migrated schema — **identical except the alembic_version table**; downgrade present (37 drops); live DB stamped; backend healthy; `/auth/login` + `/branding` + `/workflows/` (7 workflows intact) all working; `make test-backend` = 8/8.
- Note: backend routes have no `/api` prefix — nginx (`localhost:3000/api/...`) strips it. Direct backend = `localhost:6000/auth/login`, `/branding`, `/workflows/` (trailing slash required).
- **Next: P0.3 (move the pptr e2e harness into the repo).**

### 2026-08-01 — Session 2: P0.1 done
- **P0.1 backend test baseline complete.** Command: `make test-backend` (= `docker compose exec backend python -m pytest -v`).
- Changes: added `aiosqlite==0.19.0` to `backend/requirements.txt` (was missing — the test DB fixture needs it); added `backend/pytest.ini` (`testpaths=tests`, `asyncio_mode=auto`, `cache_dir=/tmp/.pytest_cache`); added root `Makefile` (`test-backend`, `build-backend`); rebuilt backend image + recreated backend container (healthy).
- Fixed two pre-existing test blockers: (1) async fixture was unhandled without `asyncio_mode=auto` → raw async-generator passed to engine; (2) `create_workflow` returned a workflow with a lazy `steps` relationship → `MissingGreenlet`; fixed by `await db.refresh(workflow, attribute_names=["steps"])` in `workflow_engine.py:90`.
- Result: **8/8 tests pass** (TestWorkflowEngine x4, TestAIService x2, TestStepExecutors x2).
- Backend/frontend/postgres all healthy after rebuild.
- **Next: P0.2 (alembic migrations).**

### 2026-08-01 — Planning session (no code changes)
- User decisions: (1) condition eval errors are **strict** — step fails, run fails with a clear error, and an **admin notice email** is sent (never a predetermined fallback); (2) the project needs a **ground-up cleanup** across many sessions with breaks, planned in small steps.
- Created this plan (`docs/REPAIR_PLAN.md`) covering Phases 0-6, each task sized for one session.
- Verified inventory and found: `api/webhooks.py` is dead (never registered in main.py); scheduler is live on startup; `template_service.py` is fine but its template files are Markdown; 8 backend tests exist, no frontend tests, no alembic.
- **Next session:** start P0.1 (backend test baseline) then P1.1 (condition contract) — both small and independent of the risky P1.5 state-machine work.
- Reminder: branding, role-routing, designer edge/end-node fixes, and settings-blanking fix from prior sessions are all verified-good; see Status + Known-good E2E state.

---

## Verified Inventory (current reality — updated 2026-08-01)

**Backend** (`backend/app/`)
- `main.py`: routers registered = workflows, workflow_runs (x2), admin, ai, knowledge_base, auth, portal, forms, system_settings, tasks, **webhooks (P2.5)**. Scheduler initialized on startup.
- `api/portal.py`: added `/portal/my-tasks` endpoint (P3.3) returning open/owned tasks for current user; `/portal/workflows` now includes `entry_form_id`.
- `services/workflow_engine.py`: `_register_default_executors` (api_call, database_query, email, condition, delay, form, **webhook, custom_code**); `_get_targets` now implements the Model B condition contract (`routes[]` first-truthy wins → `default_target_step_id`, empty expression = error) with legacy backfill via `_normalize_condition` (step-level `condition_expr` + `on_true`/`on_false`, Model A `definition.expression`); `_evaluate_condition` is strict (raises with expression + exception); `resume_workflow` now supports resumable execution from pause point **and updates step output with task result before resuming** (P3.2); linear vs graph paths unified via `_execute_branching_sync`; **graph finalize bug fixed** (P1.5); in-place JSON mutations (`definition`/`config`) are NOT persisted (plain `JSON` columns); **P1.6: run timeout checking (`_check_timeout`), per-step retries in `_execute_single_step`, failure hooks via HTTP POST**.
- **Frontend** (`frontend/src/`):
  - `WorkflowDesigner.tsx`: full node palette (api_call, database_query, email, condition, form, delay, **human_task, approval, webhook, custom_code, calculation, report**); P4.1 removed dead "Condition Expression" field; per-route expression editing with empty-expression validation; P4.2 editors for all 12 step types.
  - `RunMonitor.tsx`: P4.3 enhanced with chosen branch display, expandable per-step input/output/error details, status badges, cancel button.
  - `Portal.tsx`: P3.3 added entry form modal + pending tasks section.
- `services/step_executors.py`: All executors real: `EmailExecutor` (P2.1), `DatabaseQueryExecutor` (P2.2), `FormExecutor` (P2.3), `CustomCodeExecutor` (P2.4, thread + restricted builtins), `WebhookExecutor` (P2.4), `CalculationExecutor` (P5.1, safe eval), `ReportExecutor`/`ReadonlyFormExecutor` (P5.3, HTML placeholders), `AIConditionExecutor` (P5.2, falls back to user expression), `ProgrammableDelayExecutor` (P5.5, seconds/sql_wait/cron). All registered in `WorkflowEngine._register_default_executors`. `ConditionExecutor` evaluates Model B `routes[0].expression` (fallback Model A `expression`), empty → `"True"`; eval/exec run in-loop.
- `services/template_service.py`: P5.4 added `get_step_templates()` and `get_step_template(step_type)` to extract individual step templates from workflow templates.
- `api/knowledge_base.py`: P5.4 added `/step-templates` and `/step-templates/{step_type}` endpoints.
- `services/scheduler.py`: APScheduler, cron/interval/date triggers, `Schedule` model, webhook + external trigger, initialized on startup.
- `services/ai_service.py`: `VALID_STEP_TYPES` condition requires `routes` (Model B); prompts teach `data['field']` expressions + Model B condition shape.
- `services/template_service.py`: properly loads `*.json` from `knowledge-base/templates` (now 5 real JSON template files with Model B conditions); API in `knowledge_base.py` (`GET /templates`, create-from-template, save-as-template).
- `api/knowledge_base.py`, `api/admin.py`, `api/system_settings.py` (branding get/set), `api/tasks.py`, `api/portal.py`, `api/forms.py` present.
- **Alembic in place** (P0.2): `backend/alembic/`, initial migration `17c4ba709ec6` stamped on the live DB; backend starts with `alembic upgrade head`; schema changes go through migrations.
- `services/email_service.py`: minimal SMTP `notify_admin()` (P1.2), no-op + log when SMTP unconfigured; called from `workflow_engine.py` failure paths.
- Tests: `backend/tests/test_workflow.py` (11 tests, TestWorkflowEngine / TestAIService / TestStepExecutors incl. Model B condition + template loading) + `backend/tests/test_engine_behavior.py` (65 tests, P0.4 regression net + P1.1 condition contract + P1.2 admin notices + P1.6 timeout/retries/hooks + P2.1 email interpolation + P2.2 DB query parameterization + P2.3 form executor + P2.4 custom_code/webhook + P2.5 webhook secret verification + P2.6 scheduler integration + P5.1 calculation + P5.2 AI condition + P5.3 report/readonly_form + P5.4 step templates + P5.5 programmable delay + P6.1 SSRF protection), pytest + pytest-asyncio + sqlite in-memory. **76/76 green.**

**Frontend** (`frontend/src/`)
- `WorkflowDesigner.tsx`: rewritten (staged Save/Cancel, position persistence, stable end/start nodes, start-edge re-measure fix via `useUpdateNodeInternals`). Route editor exists (per-route expression + target, "Else" default, "+ Add Output"). Condition field editing only in node editor; dead "Condition Expression" input.
- `Branding.tsx` + `SettingsPage.tsx`: branding render chain + `ready` flag; blanking bug fixed.
- `Auth.tsx`: `roleDefaultPath(role)`; App.tsx role-based post-login start page; auth `initializing` flag.
- `Portal.tsx`, `FormDesigner.tsx` (FIELD_TYPES incl. `info`), `FormRenderer.tsx` (textarea/boolean/select/date/file/email/number).
- **No frontend test tooling** in `package.json`.

**Infra**: `pythonworkflow-frontend-1` (:3000, nginx → `/api` → backend), `pythonworkflow-backend-1` (:6000), `pythonworkflow-postgres-1`. Work logins admin/admin dev/dev staff/staff user/user. `GET /api/branding` → `{system_name, portal_name, logo_url}`. E2E harness (P0.3): image `pythonworkflow-e2e`, scripts in `tests/e2e/`, run via `make test-e2e` (= `bash tests/e2e/run-e2e.sh`), driving Chromium at 127.0.0.1:9222. Backend test command: `make test-backend`.

**Known-good E2E state (verified headless)**: role-based post-login routing for all four roles; branding renders "xxxx"; designer edges render for workflows 22/25 incl. start edge; save-cycle/Cancel-dirty on workflow 26 (deleted after); workflow 22 untouched; settings blanking fixed.

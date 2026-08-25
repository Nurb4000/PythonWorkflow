# Shared Store Playbook

**Purpose:** Sanctioned patterns for using CMDB lookup/update + DB query steps
as integration hubs between workflows. Replaces the unofficial hacks people
currently use.

---

## Guiding principles

1. **One source of truth per concept** — if two workflows need "cost center",
   define it once in a CI type or a shared form, reference by ID.
2. **Write once, read many** — prefer CMDB update steps for canonical writes,
   lookup steps for reads. Avoid parallel writes to the same row.
3. **Idempotent writes** — use `upsert` semantics (match on unique key, update
   if exists, insert if not). See `DatabaseQueryExecutor` UPSERT support.
4. **Audit everything** — all writes go through `log_custom_field_audit` or
   equivalent. Never bypass audit for "performance".
5. **Respect table ownership** — only the workflow that "owns" a concept should
   write to its canonical table. Other workflows read.

---

## Fair-game tables

| Table | Owned by | Write access | Read access |
|-------|----------|--------------|-------------|
| `configuration_items` | CMDB admin | Admin + CMDB workflows | All workflows |
| `forms` / `form_submissions` | Form creator | Form creator workflow | Portal users |
| `workflows` / `workflow_runs` | Workflow engine | Engine only | Admin/owner |
| `tasks` | Task system | Task system | Assigned user + admin |

**Do NOT write to:** `users`, `groups`, `system_settings`, `alembic_version`,
`workflow_steps` (structure), `step_instances` (history).

---

## Pattern 1: Workflow A writes → Workflow B reads

```
Workflow A (data entry):
  1. Form step captures user input
  2. CMDB update step writes to shared CI type
  3. Webhook/fire-and-forget triggers Workflow B

Workflow B (consumer):
  1. CMDB lookup step reads the CI
  2. Process the data
```

**Why this works:** Decouples timing. Workflow B doesn't need to wait for A.
Use the async trigger (B3 async handoff) for this pattern.

---

## Pattern 2: Synchronous sub-workflow call

```
Parent workflow:
  1. ...
  2. Sub-workflow step calls Child workflow (sync)
  3. Child returns result_data
  4. Parent continues with result

Child workflow:
  1. Receives $input.* from parent
  2. Processes
  3. Returns result via sub-workflow response
```

**When to use:** When the parent needs the child's result to continue.
Example: validation workflow that must pass before main workflow proceeds.

**Implementation:** See B3 — synchronous sub-workflow step (in progress).

---

## Pattern 3: Shared lookup table via CMDB

For data multiple workflows need (e.g., "cost centers", "departments"):

1. Create a CI type (e.g., `cost_center`) with fields: `code`, `name`, `active`
2. Seed with initial data via admin UI or script
3. Workflows read via CMDB lookup step, filter by `active = true`
4. Updates go through a single "master" workflow (governed by B4)

**Benefit:** Single source of truth, no drift between workflows.

---

## Write etiquette

1. **Use parameters, not literals** — always pass values via `$input.*`, never
   hardcode in step definitions.
2. **Validate before write** — use Calculation steps to check data quality
   before committing to shared tables.
3. **Handle conflicts** — if upsert fails, log and retry with backoff (see
   ProgrammableDelayExecutor).
4. **Audit trail** — every write should have a corresponding audit log entry.
   Use `log_custom_field_audit` or equivalent.

---

## Worked example: Employee onboarding

**Scenario:** HR submits new employee data → IT provisions account → Finance
sets up payroll.

```
Workflow 1 (HR Entry):
  Form: name, email, department, start_date
  → CMDB update: create/update CI in `employees` type
  → Async trigger: Workflow 2

Workflow 2 (IT Provisioning):
  → CMDB lookup: get employee CI by email
  → API call: create account in identity provider
  → DB query: insert into `it_access` table
  → Async trigger: Workflow 3

Workflow 3 (Finance):
  → CMDB lookup: get employee CI
  → DB query: insert into `payroll_setup` table
  → Email step: notify employee
```

**Key design decisions:**
- Employee CI is the shared anchor (Pattern 3)
- Workflows 2 and 3 are async (Pattern 1) — HR doesn't wait
- Each workflow owns its write table (`it_access`, `payroll_setup`)
- Audit logs track every CMDB update

---

## Migration path for existing hacks

If you currently have workflows that:
- Write directly to tables they don't own → refactor to use CMDB lookup/update
- Share data via file drops → move to shared CI types
- Use hardcoded IDs across workflows → parameterize via `$input.*`

**Priority order:**
1. Fix writes to `users`/`groups`/`system_settings` (security risk)
2. Fix parallel writes to same CI type (data corruption risk)
3. Refactor file-drop integrations (fragile, slow)

---

*This playbook is a living document. Add patterns as they emerge.*

# Run Context Rules

**Purpose:** Document how data flows through a workflow run — what `$input.*`
resolves to, when `result_data` is available, and how steps see upstream data.

---

## Data flow overview

```
Entry Form Input
       │
       ▼
  ┌─────────┐
  │ Step 1   │ ──result_data──┐
  └─────────┘                 │
       │                     ▼
       ▼              ┌─────────┐
  ┌─────────┐         │ Step 2   │ ──result_data──┐
  │ Step N   │         └─────────┘                 │
  └─────────┘                                      ▼
       │                                      ┌─────────┐
       └──────────────────────────────────────│ Final    │
                                              │ Step     │
                                              └─────────┘
```

Each step receives:
- **`$input.*`**: Resolved from entry form + upstream `result_data`
- **`step_definition`**: The step's config from the workflow definition

Each step produces:
- **`result_data`**: Merged into the run context for downstream steps
- **`status`**: completed/failed/skipped

---

## `$input.*` resolution order

When a step references `$input.field_name`:

1. **Entry form fields** — fields from the workflow's entry form schema
2. **Upstream `result_data`** — merged in workflow-step order (step 1 → step 2 → ...)
3. **Step definition defaults** — if configured in the step

**Conflict resolution:** Later sources override earlier ones. `result_data` from
step N overrides entry form fields.

---

## `result_data` merging

Result data is merged shallowly (top-level keys only):

```python
# Pseudocode
run_context = dict(entry_form_data)
for step in workflow_steps:
    result = execute_step(step, run_context)
    if result and isinstance(result, dict):
        run_context.update(result)  # shallow merge
```

**Implication:** If step 1 returns `{"user": {"name": "Alice"}}` and step 2
returns `{"user": {"email": "alice@example.com"}}`, the final context has:
`{"user": {"email": "alice@example.com"}}` — step 2's `user` object replaces
step 1's entirely.

**Workaround:** Use nested keys that don't collide, or merge explicitly in a
Calculation step.

---

## When is data available?

| Timing | Available data |
|--------|---------------|
| Step 1 executes | Entry form data only |
| Step 2 executes | Entry form + Step 1 result_data |
| Step N executes | Entry form + Steps 1..N-1 result_data |
| Run completes | All result_data merged |

---

## Debugging missing data

If a step can't find `$input.field`:

1. Check the entry form schema — is the field defined?
2. Check upstream steps — did they return `result_data` with that key?
3. Check for naming mismatches — `$input.cost_center` vs `$input.costCentre`
4. Use the **Run Inspector** (Phase B2) to see resolved context at each step

---

## Example: Employee onboarding run context

```
Entry form: {name, email, department, start_date}

Step 1 (API call to HR system):
  result_data: {employee_id: 123, hr_status: "active"}

Step 2 (DB query — uses $input.employee_id):
  input resolved: employee_id=123 (from step 1)
  result_data: {it_account_created: true}

Step 3 (Email — uses $input.name, $input.email):
  input resolved: name="Alice", email="alice@example.com" (from entry form)
```

---

*This document complements `SHARED_STORE_PLAYBOOK.md`.*

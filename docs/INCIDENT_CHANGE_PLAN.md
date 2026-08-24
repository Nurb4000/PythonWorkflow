# Incident & Change Demo Workflows — Implementation Plan

## Progress

| Phase | Status | Completed Items |
|-------|--------|-----------------|
| **Phase 0 — Framework Extensions** | ✅ COMPLETE | 0.1 DateTarget tracking model, 0.2 DateTarget scheduler, 0.3 API endpoints, 0.4 CalculationExecutor extension |
| **Phase 1 — Demo Data Setup** | ✅ COMPLETE | 1.1 Services & Categories, 1.2 Groups with OLA, 1.3 Seeding script |
| **Phase 2 — Incident Demo Workflow** | ✅ COMPLETE | 2.1 XML workflow package, 2.2 Marketplace registration, 2.3 Verification |
| **Phase 3 — Change Demo Workflow** | ✅ COMPLETE | 3.1 XML workflow package, 3.2 DateTarget integration, 3.3 Marketplace registration, 3.4 Verification |
| **Phase 4 — Frontend Enhancements** | ⏳ IN PROGRESS | 4.1 DateTarget admin widget ✅, 4.2 Task date badge ✅, 4.3 Run inspector date display |

### Session Log

- **2026-08-13**: Phase 0 complete. Created DateTarget model (backend/app/models/date_targets.py) with workflow_run_id, step_id, task_id, target_key, target_datetime, status columns. Alembic migration a1b2c3d4d5e6 chains from e0f1a2b3c4d5 (OLA). API router at /date-targets with list, stats, create, update, delete endpoints. Scheduler extended with _check_date_target_breaches() running every 5 min alongside SLA monitor. CalculationExecutor extended — when step definition includes date_target_key, evaluated result is parsed as ISO datetime and a DateTarget record is created. Engine injects _workflow_run_id into step input_data for executor access. All files compile clean, routes verified in OpenAPI schema (145 total paths, 3 date-target paths).
- **2026-08-13**: Phase 1 complete. Created demo_data_service.py with idempotent seeding for 1 category (IT Operations), 2 services (IT Service Desk, IT Change Management) each with per-priority SLA targets, and 9 groups (IT Triage Team, Network Team, Server Team, Application Team, QC Verification Team, Managers, Team Supervisors, Change Advisory Board, Change Implementation Team) each with per-priority OLA pickup/closure targets. Seeding returns group name→ID mapping for workflow installer to resolve assigned_group_id references.
- **2026-08-13**: Phase 2 complete. Created incident-management.xml with 10 steps (entry form → triage → condition router → 4 team implementations → QC condition → QC verification → email notification), 4 forms (entry, triage, implementation, QC), and 5 groups. Registered in DEMO_METADATA. XML validates correctly with proper JSON schemas, step routing, and group references.
- **2026-08-13**: Phase 3 complete. Created change-management.xml with 9 steps (entry form → manager approval → supervisor approval → CAB review → calculation date target → implementation → PIR → email complete/reject), 6 forms (RFC entry, manager approval, supervisor approval, CAB review, implementation, PIR), and 4 groups. Step 5 uses CalculationExecutor with date_target_key="change_target_completion" to create a DateTarget record from the target_end_date field. All three approval steps route to rejection email on "rejected" decision. Registered in DEMO_METADATA. XML validates correctly.
- **2026-08-13**: Cosmetic — Form quick-actions added to WorkflowDesigner and WorkflowDetail. When a form is selected in a step's form_id dropdown (form, human_task, approval steps) or the workflow-level entry form selector, three buttons appear: 👁 Preview (opens FormDesigner in preview mode via `?preview=N`), ✏️ Edit (opens FormDesigner for editing via `?editing=1&id=N`), and + New Form (opens FormDesigner to create a new form). FormDesigner now supports URL params `?preview=N` and `?editing=1&id=N` to auto-load the specified form on mount.
- **2026-08-23**: Phase 4.1 complete. `DateTargetWidget.tsx` added — collapsible admin dashboard card with stats chips (pending / breached last 30 days / compliance %) and a breached-targets table linking into the run inspector. `dateTargetsApi` added to `frontend/src/services/api.ts` (list + stats endpoints). Mounted on AdminDashboard alongside SLA/OLA widgets.
- **2026-08-24**: Housekeeping note — commit d952ad9 accidentally overwrote this file with a copy of the cleanup plan; original plan restored from history (95200d0) before starting 4.2. Active backlog tracking now lives in `docs/CLEANUP_PLAN.md`.
- **2026-08-24**: Phase 4.2 complete. New `frontend/src/components/DateTargetBadge.tsx`: badge states per plan — green "On track" (>24h away), yellow "Due soon" (<24h), red "Breached"; status "met" renders green "Met". Targets resolve at the RUN level (calc steps create DateTarget rows without task_id), so each task maps via its `workflow_run_id`; when a run has several targets, `pickRunTarget` surfaces breached first, then earliest pending, met last. Backend: `GET /date-targets` gained a comma-separated `run_ids` batch filter so dashboards decorate all runs in one request (plus list now excludes soft-deleted targets). Wired into AdminTaskDashboard + RoleTaskDashboard as a hideable "Date Target" column (CSV-aware) and TaskDetail details grid. Verified: tsc clean; suite 145 passing (141 baseline + 4 new date-target tests). Remaining in Phase 4: 4.3 run-inspector date display.

---

## Overview

Build two demo workflows that showcase the system's ability to handle **Incident Management** and **Change Management** patterns — extending beyond the existing service request demos. Both leverage the existing workflow engine, SLA/OLA tracking, approval steps, conditional routing, and CMDB integration. Packaged as marketplace demos for easy import.

### Design Principles

- **No new step types** — use existing `form`, `human_task`, `approval`, `condition`, `email`, `calculation` steps
- **Minimal schema changes** — extend via `custom_data` JSON columns where possible
- **Service-based** — both workflows tie to services for SLA tracking and reporting
- **Multi-team** — demonstrate tasks flowing between groups with OLA tracking
- **Marketplace-ready** — packaged as XML demo imports, consistent with existing patterns

---

## Phase 0 — Framework Extensions (Date-Based Targets)

**Why**: Change management tracks a **target completion date** (calendar date), not a time-based OLA (hours from creation). The existing `ola_closure_target_hours` on tasks won't work for this. We need a lightweight mechanism to track date-based targets and detect breaches.

**Effort**: ~1 session

### 0.1 Database: `date_targets` table

Lightweight tracking table for date-based targets (used by change workflows, potentially other flows later).

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `workflow_run_id` | FK → `workflow_runs` | The run this target belongs to |
| `step_id` | FK → `workflow_steps` (nullable) | Specific step, or null for run-level |
| `task_id` | FK → `tasks` (nullable) | Specific task |
| `target_key` | String | Semantic key: `change_target_completion`, `incident_escalation_by`, etc. |
| `target_datetime` | Timestamp | The deadline |
| `status` | String | `pending`, `met`, `breached` |
| `custom_data` | JSONB | Extensible metadata |
| `created_at` | Timestamp | |

**Migration**: New alembic migration file.

### 0.2 Model & Service

New file: `backend/app/models/date_targets.py`
- `DateTarget` SQLAlchemy model

New service methods in `backend/app/services/scheduler.py`:
- `_check_date_target_breaches()` — runs every 5 min alongside SLA checker
- Marks `status = 'breached'` for any pending target where `now > target_datetime`
- Sends admin notification email (reuse existing `notify_admin()`)

### 0.3 API Endpoints

New router: `backend/app/api/date_targets.py`

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/date-targets?run_id=N` | Any | List targets for a run |
| POST | `/date-targets` | Admin/Staff | Create a date target |
| PATCH | `/date-targets/{id}` | Admin/Staff | Update status (mark met) |

Registered in `backend/app/main.py`.

### 0.4 Calculation Step Extension

The existing `calculation` step executor will create `DateTarget` records when its definition includes a `date_target_key` field. This allows workflow steps to declaratively set date targets without custom code.

Extend `CalculationExecutor` in `backend/app/services/step_executors.py`:
- If step definition has `date_target_key`, evaluate the expression to produce a datetime string
- Create a `DateTarget` record linked to the current run/step
- Store target datetime in both `DateTarget` and step `output_data`

### 0.5 Frontend: Admin Widget

On `/admin` dashboard, add a small card:
- Count of pending date targets
- Count of breached date targets (last 30 days)
- Compliance percentage

Reuses existing admin dashboard pattern from SLA/OLA widgets.

---

## Phase 1 — Demo Data Setup

**Why**: The demo workflows reference services, categories, and groups that need to exist for a meaningful out-of-box experience. A seeding script creates them idempotently on first demo install.

**Effort**: ~0.5 session (can combine with Phase 2 or 3)

### 1.1 Services & Categories

Create via seeding script (SQL or API calls during demo install):

**Category**: "IT Operations"
- `key`: `it_operations`
- `icon`: `⚙️`

**Service**: "IT Service Desk" (for incidents)
- `key`: `it_service_desk`
- `category_id`: IT Operations
- `icon`: `🎧`
- `description`: "General IT support — report incidents, get things fixed"
- `support_group_id`: group-it-triage
- `custom_data`:
  ```json
  {
    "sla_targets": {
      "response_hours": { "1": 0.5, "2": 1, "3": 4, "4": 8 },
      "resolution_hours": { "1": 4, "2": 8, "3": 24, "4": 72 }
    }
  }
  ```

**Service**: "IT Change Management" (for changes)
- `key`: `it_change_management`
- `category_id`: IT Operations
- `icon`: `🔄`
- `description`: "Submit and track infrastructure and application changes"
- `support_group_id`: group-it-triage
- `custom_data`:
  ```json
  {
    "sla_targets": {
      "response_hours": { "1": 1, "2": 4, "3": 8, "4": 24 },
      "resolution_hours": { "1": 24, "2": 72, "3": 168, "4": 336 }
    }
  }
  ```

### 1.2 Groups with OLA Targets

| Group ID | Name | Type | OLA Targets (custom_data) |
|----------|------|------|---------------------------|
| `group-it-triage` | IT Triage Team | internal | pickup: {1:0.25, 2:1, 3:2, 4:4}, closure: {1:1, 2:4, 3:8, 4:16} |
| `group-network-team` | Network Team | internal | pickup: {1:0.5, 2:2, 3:4, 4:8}, closure: {1:4, 2:8, 3:24, 4:48} |
| `group-server-team` | Server Team | internal | pickup: {1:0.5, 2:2, 3:4, 4:8}, closure: {1:4, 2:8, 3:24, 4:48} |
| `group-app-team` | Application Team | internal | pickup: {1:0.5, 2:2, 3:4, 4:8}, closure: {1:4, 2:8, 3:24, 4:48} |
| `group-qc-team` | QC Verification Team | internal | pickup: {1:1, 2:4, 3:8, 4:16}, closure: {1:4, 2:8, 3:24, 4:48} |
| `group-managers` | Managers | internal | pickup: {1:0.5, 2:2, 3:4, 4:8}, closure: {1:2, 2:8, 3:16, 4:24} |
| `group-team-supervisors` | Team Supervisors | internal | pickup: {1:0.5, 2:2, 3:4, 4:8}, closure: {1:2, 2:8, 3:16, 4:24} |
| `group-cab` | Change Advisory Board | internal | pickup: {1:1, 2:4, 3:8, 4:16}, closure: {1:4, 2:8, 3:24, 4:48} |
| `group-change-impl-team` | Change Implementation Team | internal | pickup: {1:0.5, 2:2, 3:4, 4:8}, closure: {1:8, 2:24, 3:72, 4:168} |

### 1.3 Seeding Script

New file: `backend/app/services/demo_data_service.py`

Function `seed_incident_change_demo_data(db)` that:
1. Creates categories (idempotent by key)
2. Creates services with SLA targets (idempotent by key)
3. Creates groups with OLA targets (idempotent by name)
4. Returns mapping of group names → group IDs for use by workflow installer

Called from the marketplace install endpoint when installing incident or change demos. If groups/services already exist, reuses them.

---

## Phase 2 — Incident Demo Workflow

**Why**: Demonstrates multi-team incident handling with SLA tracking, triage-based routing, and optional QC verification.

**Effort**: ~1 session

### 2.1 Workflow Design

```
Entry Form (incident report)
    ↓
[Triage] — IT Triage Team investigates, categorizes, assigns priority
    ↓
[Category Router] — condition step routes based on triage category
    ├─ Network → [Network Team Implementation]
    ├─ Server → [Server Team Implementation]
    ├─ Application → [App Team Implementation]
    └─ Other → [Triage Team handles directly]
    ↓
[QC Verification] — QC team confirms resolution with customer (optional, conditionally enabled)
    ↓
[Close & Notify] — email to affected user, update status
```

### 2.2 Entry Form Schema

Common incident fields in a multi-column layout:

```json
{
  "type": "object",
  "columns": 2,
  "properties": {
    "incident_heading": {
      "type": "info",
      "title": "Incident Report",
      "content": "Report an IT issue. The triage team will assess and route your incident to the appropriate support team.",
      "text_align": "left",
      "required": false
    },
    "affected_user": {
      "type": "string",
      "title": "Affected User / Name",
      "required": true,
      "column": 0,
      "data_size": "medium"
    },
    "affected_email": {
      "type": "email",
      "title": "Affected User Email",
      "required": true,
      "column": 1,
      "data_size": "medium"
    },
    "department": {
      "type": "select",
      "title": "Department",
      "required": true,
      "column": 0,
      "options": ["Engineering", "Finance", "HR", "IT", "Operations", "Sales", "Other"],
      "data_size": "medium"
    },
    "device_or_system": {
      "type": "string",
      "title": "Device / System Affected",
      "required": false,
      "column": 1,
      "data_size": "medium"
    },
    "ci_ref": {
      "type": "string",
      "title": "CMDB CI Reference (optional)",
      "required": false,
      "column": 0,
      "data_size": "small"
    },
    "urgency": {
      "type": "select",
      "title": "Urgency",
      "required": true,
      "column": 1,
      "options": ["1-Critical", "2-High", "3-Medium", "4-Low"],
      "data_size": "medium"
    },
    "impact": {
      "type": "select",
      "title": "Business Impact",
      "required": true,
      "column": 0,
      "options": ["1-Single user", "2-Department", "3-Multiple departments", "4-Entire organization"],
      "data_size": "medium"
    },
    "category": {
      "type": "select",
      "title": "Issue Category",
      "required": true,
      "column": 1,
      "options": ["Network", "Server", "Application", "Hardware", "Software", "Access/Permissions", "Other"],
      "data_size": "medium"
    },
    "issue_description": {
      "type": "textarea",
      "title": "Issue Description",
      "required": true,
      "column": 0,
      "data_size": "long"
    },
    "steps_to_reproduce": {
      "type": "textarea",
      "title": "Steps to Reproduce (if applicable)",
      "required": false,
      "column": 1,
      "data_size": "long"
    },
    "workaround_attempted": {
      "type": "string",
      "title": "Workaround Attempted",
      "required": false,
      "column": 0,
      "data_size": "long"
    }
  },
  "required": ["affected_user", "affected_email", "department", "urgency", "impact", "category", "issue_description"]
}
```

### 2.3 Triage Task Form

What the triage team sees and fills:

```json
{
  "type": "object",
  "columns": 2,
  "properties": {
    "triage_heading": {
      "type": "info",
      "title": "Incident Triage",
      "content": "Review the reported incident. Assess actual priority, confirm category, and provide initial notes. The workflow will route to the appropriate team based on your category selection.",
      "text_align": "left",
      "required": false
    },
    "affected_user": { "type": "string", "title": "Affected User", "required": false, "column": 0, "data_size": "medium", "source": "form" },
    "affected_email": { "type": "string", "title": "Email", "required": false, "column": 1, "data_size": "medium", "source": "form" },
    "issue_description": { "type": "string", "title": "Issue Description", "required": false, "column": 0, "data_size": "long", "source": "form" },
    "category": { "type": "string", "title": "Reported Category", "required": false, "column": 1, "data_size": "medium", "source": "form" },
    "triage_priority": {
      "type": "select",
      "title": "Assessed Priority",
      "required": true,
      "column": 0,
      "options": ["1-Critical", "2-High", "3-Medium", "4-Low"],
      "data_size": "medium",
      "source": "form"
    },
    "triage_category": {
      "type": "select",
      "title": "Route To (Team)",
      "required": true,
      "column": 1,
      "options": ["Network Team", "Server Team", "Application Team", "Handle in Triage"],
      "data_size": "medium",
      "source": "form"
    },
    "enable_qc": {
      "type": "select",
      "title": "Require QC Verification?",
      "required": true,
      "column": 0,
      "options": ["Yes", "No"],
      "data_size": "small",
      "source": "form"
    },
    "triage_notes": {
      "type": "textarea",
      "title": "Triage Notes / Initial Assessment",
      "required": false,
      "column": 0,
      "data_size": "long",
      "source": "form"
    }
  },
  "required": ["triage_priority", "triage_category"]
}
```

### 2.4 Implementation Task Form (shared by all teams)

```json
{
  "type": "object",
  "columns": 2,
  "properties": {
    "impl_heading": {
      "type": "info",
      "title": "Incident Resolution",
      "content": "Resolve the incident. Document your actions and resolution details.",
      "text_align": "left",
      "required": false
    },
    "affected_user": { "type": "string", "title": "Affected User", "required": false, "column": 0, "data_size": "medium", "source": "form" },
    "triage_category": { "type": "string", "title": "Assigned Team", "required": false, "column": 1, "data_size": "medium", "source": "form" },
    "issue_description": { "type": "string", "title": "Issue", "required": false, "column": 0, "data_size": "long", "source": "form" },
    "triage_notes": { "type": "string", "title": "Triage Notes", "required": false, "column": 1, "data_size": "long", "source": "form" },
    "resolution_description": {
      "type": "textarea",
      "title": "Resolution Description",
      "required": true,
      "column": 0,
      "data_size": "long",
      "source": "form"
    },
    "resolution_code": {
      "type": "select",
      "title": "Resolution Code",
      "required": true,
      "column": 1,
      "options": ["Fixed", "Workaround Applied", "User Error — Resolved", "Duplicate Incident", "Cannot Reproduce", "Deferred to Change"],
      "data_size": "medium",
      "source": "form"
    },
    "impl_notes": {
      "type": "textarea",
      "title": "Additional Notes",
      "required": false,
      "column": 0,
      "data_size": "long",
      "source": "form"
    }
  },
  "required": ["resolution_description", "resolution_code"]
}
```

### 2.5 QC Verification Form

```json
{
  "type": "object",
  "columns": 2,
  "properties": {
    "qc_heading": {
      "type": "info",
      "title": "QC Verification",
      "content": "Contact the affected user to confirm the incident is fully resolved to their satisfaction.",
      "text_align": "left",
      "required": false
    },
    "affected_user": { "type": "string", "title": "Affected User", "required": false, "column": 0, "data_size": "medium", "source": "form" },
    "affected_email": { "type": "string", "title": "Email", "required": false, "column": 1, "data_size": "medium", "source": "form" },
    "resolution_description": { "type": "string", "title": "Resolution", "required": false, "column": 0, "data_size": "long", "source": "form" },
    "customer_confirmed": {
      "type": "select",
      "title": "Customer Confirmed Resolved?",
      "required": true,
      "column": 0,
      "options": ["Yes — Satisfied", "No — Requires Further Action"],
      "data_size": "medium",
      "source": "form"
    },
    "qc_notes": {
      "type": "textarea",
      "title": "QC Notes",
      "required": false,
      "column": 1,
      "data_size": "long",
      "source": "form"
    }
  },
  "required": ["customer_confirmed"]
}
```

### 2.6 Step Definitions (XML)

```
step-1: form — "Report Incident" → entry form, next: step-2
step-2: human_task — "Triage Assessment" → group-it-triage, triage form, next: step-3
step-3: condition — "Route by Category" → routes based on triage_category:
    - "data['triage_category'] == 'Network Team'" → step-4
    - "data['triage_category'] == 'Server Team'" → step-5
    - "data['triage_category'] == 'Application Team'" → step-6
    - default → step-7 (Handle in Triage)
step-4: human_task — "Network Team Resolution" → group-network-team, impl form, next: step-8
step-5: human_task — "Server Team Resolution" → group-server-team, impl form, next: step-8
step-6: human_task — "Application Team Resolution" → group-app-team, impl form, next: step-8
step-7: human_task — "Triage Team Resolution" → group-it-triage, impl form, next: step-8
step-8: condition — "QC Required?" → routes based on enable_qc:
    - "data['enable_qc'] == 'Yes'" → step-9
    - default → step-10
step-9: human_task — "QC Verification" → group-qc-team, qc form, next: step-10b or step-10
    routes:
    - "data['customer_confirmed'] == 'No — Requires Further Action'" → step-2 (re-triage loop)
    - default → step-10
step-10: email — "Notify Resolution" → affected user email
```

### 2.7 XML File

New file: `backend/app/data/demo-workflows/incident-management.xml`

Follows the same `WorkflowPackage` structure as existing demos. Includes:
- `<Workflow>` with all steps, forms, groups, and permissions
- `<Forms>` section with all 4 forms (entry, triage, implementation, QC)
- `<Groups>` section with all 6 groups (triage, network, server, app, QC, managers)
- Service reference via `service_id` on workflow (will be resolved at install time)

### 2.8 Marketplace Registration

Add to `DEMO_METADATA` in `backend/app/main.py`:
```python
"incident-management.xml": {
    "name": "Incident Management",
    "description": "Multi-team incident handling with triage routing, SLA tracking, and optional QC verification. Demonstrates break-fix workflow patterns.",
    "category": "IT Operations",
    "tags": ["demo", "incident", "triage", "sla", "multi-team", "itil"],
}
```

---

## Phase 3 — Change Demo Workflow

**Why**: Demonstrates multi-stage approval chains, CAB review, date-targeted implementation, and post-implementation review.

**Effort**: ~1 session

### 3.1 Workflow Design

```
Entry Form (change request)
    ↓
[Submitter Manager Approval] — first gate: does the submitter's manager approve?
    ↓ (approved)
[Affected Team Supervisor Approval] — second gate: does the impacted team agree?
    ↓ (approved)
[CAB Review] — Change Advisory Board final approval with risk assessment
    ↓ (approved)
[Calculate Target Date] — calculation step sets date-based target from change window
    ↓
[Implement Change] — assigned team executes, tracked against target date (NOT OLA hours)
    ↓
[Post-Implementation Review] — document success/failure, lessons learned
    ↓
[Notify & Close] — email stakeholders, update records
```

Rejection at ANY approval step → notification to submitter → end.

### 3.2 Entry Form Schema

Comprehensive change request fields:

```json
{
  "type": "object",
  "columns": 2,
  "properties": {
    "change_heading": {
      "type": "info",
      "title": "Request for Change (RFC)",
      "content": "Submit a change request for review and approval. All changes go through manager approval, affected team sign-off, and Change Advisory Board (CAB) review.",
      "text_align": "left",
      "required": false
    },
    "change_title": {
      "type": "string",
      "title": "Change Title",
      "required": true,
      "column": 0,
      "data_size": "long"
    },
    "requester_name": {
      "type": "string",
      "title": "Requester Name",
      "required": true,
      "column": 1,
      "data_size": "medium"
    },
    "requester_email": {
      "type": "email",
      "title": "Requester Email",
      "required": true,
      "column": 0,
      "data_size": "medium"
    },
    "change_type": {
      "type": "select",
      "title": "Change Type",
      "required": true,
      "column": 1,
      "options": ["Standard", "Normal", "Emergency"],
      "data_size": "medium"
    },
    "service_affected": {
      "type": "select",
      "title": "Service Affected",
      "required": true,
      "column": 0,
      "options": ["Email Service", "File Storage", "Network Infrastructure", "Application Platform", "Database Services", "Other"],
      "data_size": "medium"
    },
    "ci_affected": {
      "type": "string",
      "title": "Configuration Items Affected",
      "required": false,
      "column": 1,
      "data_size": "long"
    },
    "change_description": {
      "type": "textarea",
      "title": "Change Description — What & Why",
      "required": true,
      "column": 0,
      "data_size": "long"
    },
    "implementation_plan": {
      "type": "textarea",
      "title": "Implementation Plan — How",
      "required": true,
      "column": 1,
      "data_size": "long"
    },
    "rollback_plan": {
      "type": "textarea",
      "title": "Rollback Plan",
      "required": true,
      "column": 0,
      "data_size": "long"
    },
    "risk_level": {
      "type": "select",
      "title": "Risk Level",
      "required": true,
      "column": 1,
      "options": ["Low", "Medium", "High"],
      "data_size": "small"
    },
    "risk_justification": {
      "type": "textarea",
      "title": "Risk Justification",
      "required": false,
      "column": 0,
      "data_size": "long"
    },
    "target_start_date": {
      "type": "datetime",
      "title": "Target Implementation Start",
      "required": true,
      "column": 1,
      "data_size": "medium"
    },
    "target_end_date": {
      "type": "datetime",
      "title": "Target Implementation End",
      "required": true,
      "column": 0,
      "data_size": "medium"
    },
    "outage_window": {
      "type": "select",
      "title": "Expected Outage",
      "required": true,
      "column": 1,
      "options": ["None", "Minimal (< 15 min)", "Short (15-60 min)", "Extended (1-4 hours)", "Major (> 4 hours)"],
      "data_size": "medium"
    },
    "outage_scope": {
      "type": "select",
      "title": "Outage Scope / Scale",
      "required": false,
      "column": 0,
      "options": ["Single user", "Department", "Building/Campus", "All locations", "External customers"],
      "data_size": "medium"
    },
    "test_plan": {
      "type": "textarea",
      "title": "Test Plan / Verification Steps",
      "required": false,
      "column": 0,
      "data_size": "long"
    },
    "backout_criteria": {
      "type": "textarea",
      "title": "Backout Criteria — When to Rollback",
      "required": false,
      "column": 1,
      "data_size": "long"
    }
  },
  "required": ["change_title", "requester_name", "requester_email", "change_type", "service_affected", "change_description", "implementation_plan", "rollback_plan", "risk_level", "target_start_date", "target_end_date", "outage_window"]
}
```

### 3.3 Manager Approval Form

```json
{
  "type": "object",
  "columns": 2,
  "properties": {
    "mgr_heading": {
      "type": "info",
      "title": "Manager Approval — Change Request",
      "content": "Review the change request submitted by your team member. Approve to proceed to affected team review, or reject with feedback.",
      "text_align": "left",
      "required": false
    },
    "change_title": { "type": "string", "title": "Change Title", "required": false, "column": 0, "data_size": "long", "source": "form" },
    "requester_name": { "type": "string", "title": "Requester", "required": false, "column": 1, "data_size": "medium", "source": "form" },
    "risk_level": { "type": "string", "title": "Risk Level", "required": false, "column": 0, "data_size": "small", "source": "form" },
    "outage_window": { "type": "string", "title": "Expected Outage", "required": false, "column": 1, "data_size": "medium", "source": "form" },
    "change_description": { "type": "string", "title": "Description", "required": false, "column": 0, "data_size": "long", "source": "form" },
    "approval_decision": {
      "type": "select",
      "title": "Decision",
      "required": true,
      "column": 0,
      "options": ["approved", "rejected"],
      "data_size": "small",
      "source": "form"
    },
    "manager_comments": {
      "type": "textarea",
      "title": "Manager Comments",
      "required": false,
      "column": 1,
      "data_size": "long",
      "source": "form"
    }
  },
  "required": ["approval_decision"]
}
```

### 3.4 Team Supervisor Approval Form

Similar structure, pre-filled from entry form + manager comments. Decision field routes to CAB or rejection.

### 3.5 CAB Review Form

More detailed — includes risk assessment override and scheduling confirmation:

```json
{
  "type": "object",
  "columns": 2,
  "properties": {
    "cab_heading": {
      "type": "info",
      "title": "Change Advisory Board Review",
      "content": "Final approval gate. Assess overall risk, confirm scheduling doesn't conflict with other changes, and authorize or reject.",
      "text_align": "left",
      "required": false
    },
    "change_title": { "type": "string", "title": "Change Title", "required": false, "column": 0, "data_size": "long", "source": "form" },
    "risk_level": { "type": "string", "title": "Submitted Risk", "required": false, "column": 1, "data_size": "small", "source": "form" },
    "target_start_date": { "type": "string", "title": "Target Start", "required": false, "column": 0, "data_size": "medium", "source": "form" },
    "target_end_date": { "type": "string", "title": "Target End", "required": false, "column": 1, "data_size": "medium", "source": "form" },
    "outage_window": { "type": "string", "title": "Expected Outage", "required": false, "column": 0, "data_size": "medium", "source": "form" },
    "outage_scope": { "type": "string", "title": "Outage Scope", "required": false, "column": 1, "data_size": "medium", "source": "form" },
    "implementation_plan": { "type": "string", "title": "Implementation Plan", "required": false, "column": 0, "data_size": "long", "source": "form" },
    "rollback_plan": { "type": "string", "title": "Rollback Plan", "required": false, "column": 1, "data_size": "long", "source": "form" },
    "cab_risk_assessment": {
      "type": "select",
      "title": "CAB Risk Assessment",
      "required": true,
      "column": 0,
      "options": ["Accept as Submitted", "Elevated Risk — Approved with Conditions", "Elevated Risk — Rejected"],
      "data_size": "medium",
      "source": "form"
    },
    "schedule_conflict": {
      "type": "select",
      "title": "Schedule Conflict?",
      "required": true,
      "column": 1,
      "options": ["No Conflicts", "Conflict — Reschedule Required"],
      "data_size": "medium",
      "source": "form"
    },
    "cab_conditions": {
      "type": "textarea",
      "title": "Conditions / Additional Requirements",
      "required": false,
      "column": 0,
      "data_size": "long",
      "source": "form"
    },
    "approval_decision": {
      "type": "select",
      "title": "CAB Decision",
      "required": true,
      "column": 1,
      "options": ["approved", "rejected"],
      "data_size": "small",
      "source": "form"
    },
    "cab_comments": {
      "type": "textarea",
      "title": "CAB Comments",
      "required": false,
      "column": 0,
      "data_size": "long",
      "source": "form"
    }
  },
  "required": ["cab_risk_assessment", "schedule_conflict", "approval_decision"]
}
```

### 3.6 Implementation Task Form

Includes date target tracking and success/failure outcome:

```json
{
  "type": "object",
  "columns": 2,
  "properties": {
    "impl_heading": {
      "type": "info",
      "title": "Change Implementation",
      "content": "Execute the approved change. Complete within the target window and document results.",
      "text_align": "left",
      "required": false
    },
    "change_title": { "type": "string", "title": "Change Title", "required": false, "column": 0, "data_size": "long", "source": "form" },
    "implementation_plan": { "type": "string", "title": "Implementation Plan", "required": false, "column": 0, "data_size": "long", "source": "form" },
    "rollback_plan": { "type": "string", "title": "Rollback Plan", "required": false, "column": 1, "data_size": "long", "source": "form" },
    "target_start_date": { "type": "string", "title": "Target Start", "required": false, "column": 0, "data_size": "medium", "source": "form" },
    "target_end_date": { "type": "string", "title": "Target End", "required": false, "column": 1, "data_size": "medium", "source": "form" },
    "cab_conditions": { "type": "string", "title": "CAB Conditions", "required": false, "column": 0, "data_size": "long", "source": "form" },
    "actual_start_date": {
      "type": "datetime",
      "title": "Actual Start Date/Time",
      "required": true,
      "column": 0,
      "data_size": "medium",
      "source": "form"
    },
    "actual_end_date": {
      "type": "datetime",
      "title": "Actual End Date/Time",
      "required": true,
      "column": 1,
      "data_size": "medium",
      "source": "form"
    },
    "change_outcome": {
      "type": "select",
      "title": "Change Outcome",
      "required": true,
      "column": 0,
      "options": ["Successful", "Successful with Minor Issues", "Failed — Rolled Back", "Deferred"],
      "data_size": "medium",
      "source": "form"
    },
    "outage_experienced": {
      "type": "string",
      "title": "Actual Outage Duration",
      "required": false,
      "column": 1,
      "data_size": "small",
      "source": "form"
    },
    "impl_notes": {
      "type": "textarea",
      "title": "Implementation Notes",
      "required": false,
      "column": 0,
      "data_size": "long",
      "source": "form"
    }
  },
  "required": ["actual_start_date", "actual_end_date", "change_outcome"]
}
```

### 3.7 Post-Implementation Review Form

```json
{
  "type": "object",
  "columns": 2,
  "properties": {
    "pir_heading": {
      "type": "info",
      "title": "Post-Implementation Review",
      "content": "Document lessons learned and confirm the change is stable.",
      "text_align": "left",
      "required": false
    },
    "change_title": { "type": "string", "title": "Change Title", "required": false, "column": 0, "data_size": "long", "source": "form" },
    "change_outcome": { "type": "string", "title": "Outcome", "required": false, "column": 1, "data_size": "medium", "source": "form" },
    "stable_confirmation": {
      "type": "select",
      "title": "Change Stable?",
      "required": true,
      "column": 0,
      "options": ["Yes — Stable", "No — Issues Detected"],
      "data_size": "medium",
      "source": "form"
    },
    "lessons_learned": {
      "type": "textarea",
      "title": "Lessons Learned",
      "required": false,
      "column": 0,
      "data_size": "long",
      "source": "form"
    },
    "follow_up_required": {
      "type": "select",
      "title": "Follow-Up Required?",
      "required": true,
      "column": 1,
      "options": ["Yes", "No"],
      "data_size": "small",
      "source": "form"
    },
    "follow_up_notes": {
      "type": "textarea",
      "title": "Follow-Up Notes",
      "required": false,
      "column": 0,
      "data_size": "long",
      "source": "form"
    }
  },
  "required": ["stable_confirmation", "follow_up_required"]
}
```

### 3.8 Step Definitions (XML)

```
step-1: form — "Submit Change Request" → entry form, next: step-2
step-2: approval — "Manager Approval" → group-managers, mgr form
    routes: approved → step-3, rejected → step-9
step-3: approval — "Affected Team Supervisor Approval" → group-team-supervisors, supervisor form
    routes: approved → step-4, rejected → step-9
step-4: approval — "CAB Review" → group-cab, cab form
    routes: approved → step-5, rejected → step-9
step-5: calculation — "Set Date Target" → evaluates target_end_date, creates DateTarget
    expression: "data['target_end_date']", date_target_key: "change_target_completion"
    next: step-6
step-6: human_task — "Implement Change" → group-change-impl-team, impl form
    OLA: NOT used (date target tracks instead)
    next: step-7
step-7: human_task — "Post-Implementation Review" → group-cab or group-team-supervisors, pir form
    next: step-8
step-8: email — "Notify Change Complete" → requester + stakeholders
step-9: email — "Notify Change Rejected" → requester
```

### 3.9 XML File

New file: `backend/app/data/demo-workflows/change-management.xml`

Same `WorkflowPackage` structure. Includes all forms, groups, and the DateTarget integration via calculation step.

### 3.10 Marketplace Registration

Add to `DEMO_METADATA` in `backend/app/main.py`:
```python
"change-management.xml": {
    "name": "Change Management",
    "description": "Multi-stage change approval workflow with manager sign-off, team supervisor review, CAB assessment, date-targeted implementation, and post-implementation review.",
    "category": "IT Operations",
    "tags": ["demo", "change", "approval", "cab", "date-target", "itil"],
}
```

---

## Phase 4 — Frontend Enhancements

**Why**: Make date targets visible and actionable in the UI.

**Effort**: ~0.5 session (can defer if needed)

### 4.1 Admin Dashboard Widget

New React component: `frontend/src/components/DateTargetWidget.tsx`
- Shows pending/breached/compliant counts
- Links to runs with breached targets
- Mounted on `/admin` dashboard alongside SLA/OLA widgets

### 4.2 Task Date Badge

Extend task display components to show date target when present:
- Green badge: on track (target > 24h away)
- Yellow badge: approaching (target < 24h)
- Red badge: breached (target passed)

### 4.3 Run Inspector Integration

In the run inspector view, show date targets as annotations on the timeline alongside SLA/OLA badges.

---

## File Inventory

### New Files

| File | Phase | Description |
|------|-------|-------------|
| `backend/app/models/date_targets.py` | 0.1 | DateTarget SQLAlchemy model |
| `backend/app/api/date_targets.py` | 0.3 | Date target CRUD API router |
| `backend/app/services/demo_data_service.py` | 1.3 | Seeding script for demo services/groups |
| `backend/app/data/demo-workflows/incident-management.xml` | 2.7 | Incident demo workflow package |
| `backend/app/data/demo-workflows/change-management.xml` | 3.9 | Change demo workflow package |
| `backend/alembic/versions/xxxx_add_date_targets.py` | 0.1 | Migration for date_targets table |
| `frontend/src/components/DateTargetWidget.tsx` | 4.1 | Admin dashboard widget |

### Modified Files

| File | Phase | Changes |
|------|-------|---------|
| `backend/app/main.py` | 0, 2, 3 | Register date_targets router; add DEMO_METADATA entries |
| `backend/app/services/scheduler.py` | 0.2 | Add `_check_date_target_breaches()` |
| `backend/app/services/step_executors.py` | 0.4 | Extend CalculationExecutor for date targets |
| `backend/app/core/database.py` | 0.1 | Import DateTarget model |
| `frontend/src/pages/AdminDashboard.tsx` | 4.1 | Mount DateTargetWidget |
| `frontend/src/components/TaskCard.tsx` (or equivalent) | 4.2 | Add date target badge |
| `docs/INCIDENT_CHANGE_PLAN.md` | — | This document (progress tracking) |

---

## Recommended Session Order

### Session 1: Foundation + Incident Demo
- **Phase 0**: DateTarget model, migration, API, scheduler, calculation extension
- **Phase 1**: Demo data seeding service
- **Phase 2**: Incident workflow XML, marketplace registration
- *Deliverable*: Working incident demo importable from marketplace, date target framework in place

### Session 2: Change Demo + Frontend Polish
- **Phase 3**: Change workflow XML with DateTarget integration, marketplace registration
- **Phase 4**: Admin widget, task badges, run inspector integration
- *Deliverable*: Both demos fully functional, date targets visible in UI

### Future Sessions (Stretch)
- Auto-routing suggestions based on service ownership
- Incident escalation rules (auto-escalate on SLA breach)
- Change calendar/scheduling conflict detection
- Problem management linkage (incident → problem → change)
- Service-specific incident variants (per-service workflow overrides)
- Notification channels beyond email (Slack, Teams webhooks)

---

## Risk & Dependency Analysis

| Risk | Mitigation |
|------|-----------|
| DateTarget adds new DB table | Minimal — single table, no FK constraints on existing models |
| Calculation step extension is hacky | It's opt-in via `date_target_key` in definition — doesn't affect existing calculations |
| Demo groups conflict with existing | Seeding script is idempotent — checks for existing by name/key |
| Form field types like `datetime` not supported | Check form renderer; if not supported, use `string` with format hint |
| Large XML files are hard to maintain | Each demo is self-contained; follow existing XML patterns exactly |

---

## Testing Strategy

For each session:
1. **Import test**: Install demo from marketplace, verify all entities created
2. **Run test**: Trigger workflow run, walk through each step manually
3. **Routing test**: Verify condition steps route correctly for each branch
4. **SLA/OLA test**: Confirm SLA targets populate on runs, OLA on tasks
5. **DateTarget test** (change only): Verify date target created, breach detection works
6. **Email test**: Verify notification emails send with correct interpolation

---

## Open Questions / Decisions

1. **Form `datetime` field type**: Does the form renderer support datetime inputs? If not, use `string` with a format placeholder and validate in task completion.
2. **CAB group membership**: Should the seeding script add specific users to groups, or leave that to admin configuration? (Recommendation: leave empty, let admin assign)
3. **Change implementation team**: Should this be a fixed group or dynamically assigned based on service affected? (Demo uses fixed group; future enhancement can dynamicize)
4. **Emergency change fast-track**: Should emergency changes skip some approval steps? (Out of scope for demo; the condition step pattern supports it)
5. **Incident numbering**: Should we auto-generate incident numbers (e.g., INC-0001)? (Could use a calculation step with DB query; nice-to-have for v2)

# Instant Workflow

A production-ready workflow automation platform with visual designer, AI-assisted step generation, human-in-the-loop execution, and comprehensive task management.

> **⚠️ Work in Progress:** This project is still being actively developed and is only about two-thirds complete. It functions at this point in time, but there are still major bugs and missing or confusing features. Expect breaking changes as we move forward.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (React)                         │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌──────────┐ │
│  │ Workflow    │ │ Run Monitor │ │ Portal      │ │ Admin    │ │
│  │ Designer    │ │             │ │             │ │ Dashboard│ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └──────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Backend (FastAPI)                          │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌──────────┐ │
│  │ Workflow    │ │ Task        │ │ Form        │ │ Webhook  │ │
│  │ Engine      │ │ API         │ │ API         │ │ API      │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └──────────┘ │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌──────────┐ │
│  │ Scheduler   │ │ AI Service  │ │ Email       │ │ Template │ │
│  │             │ │ (llama.cpp) │ │ Service     │ │ Service  │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └──────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Database (PostgreSQL)                        │
│  Workflows | Steps | Runs | StepInstances | Tasks | Forms       │
└─────────────────────────────────────────────────────────────────┘
```

**Multi-tenancy.** The platform uses shared-schema, column-level isolation: every tenant-owned table carries a `tenant_id`, and content queries are scoped to the authenticated user's tenant at SQL time. A user may belong to multiple tenants (`user_tenants`); `User.tenant_id` is their default/primary tenant, and the `X-Tenant-Id` request header selects the active tenant for a given call (resolved and membership-validated by `get_current_user`, applied by `scope_current_tenant`).

## Features

### Core Engine
- **Visual Workflow Designer**: Drag-and-drop interface with graph-mode execution
- **Condition Routing**: Model B condition steps with per-route expressions and default targets
- **Graph Traversal**: Fan-out/fan-in graph execution with a visited set so each step runs at most once per run (DAG semantics). Branches traverse depth-first/sequentially; converging steps wait for all static predecessors before running
- **Workflow Join (M9)**: `join` nodes collect fan-in branch outputs into one aliased object (`$input.joined`) for downstream steps, with deterministic source selection by step id or `$input` key
- **State Machine**: Runs track status (pending/running/completed/failed/waiting/timeout/cancelled)
- **Resume Support**: Human-task pauses allow workflow resumption without re-execution
- **Timeout & Retries**: Configurable run timeouts and per-step retry logic
- **Failure Hooks**: HTTP callbacks on step/run failure
- **Conditional Error Handling (M6)**: `on_failure_target_step_id` routes a failed step to a handler instead of failing the run (optional `on_failure_filter`, e.g. `data['error_type'] == 'ValueError'`), and the `try_catch` node wraps a group of nested steps with a catch subgraph and local compensation
- **Async Sub-Workflow Handoff (G8)**: `sub_workflow` steps support `execution_mode: "async"` for fire-and-forget background jobs; the step returns the child run id immediately and does not wait for — or propagate — the child's outcome (sync remains the default)

### Executors (20 types)
| Type | Description |
|------|-------------|
| `api_call` | HTTP requests with SSRF protection |
| `database_query` | Parameterized queries (SELECT/INSERT/UPDATE/DELETE/UPSERT) |
| `email` | SMTP email with `$input.*` interpolation |
| `condition` | Branching logic with Model B routes |
| `delay` | Simple sleep-based delay |
| `form` | Pulls latest form submission data |
| `webhook` | HTTP POST/GET to external endpoints |
| `custom_code` | Sandboxed Python execution in thread |
| `calculation` | Safe expression evaluation (`data['field']`) |
| `ai_condition` | AI-generated conditions with fallback |
| `report` | Renders table/graph reports |
| `readonly_form` | Displays read-only forms |
| `programmable_delay` | SQL WAITFOR/SELECT SLEEP/cron delays |
| `cmdb_lookup` | Look up CMDB configuration items by type and field criteria |
| `cmdb_update` | Update a CMDB configuration item by ID or lookup |
| `sub_workflow` | Sub-workflow invocation — sync (call, wait, merge result) or async (fire-and-forget) |
| `loop` | Iterate a collection over a nested step |
| `transform` | Rename / map / merge / join structured data |
| `try_catch` | Try/catch boundary around nested steps with optional filtering and compensation |
| `join` | Collect and alias workflow-level fan-in branch outputs (M9) |

### Human-in-the-Loop
- **Task System**: Open → Owned → Completed → Closed lifecycle
- **Assignment**: By user ID or group (role-based)
- **Portal Integration**: Pending tasks surfaced on portal home
- **Resume**: Workflow continues from pause point after task completion

### AI Assist
- **Per-Node Assist**: Generate, explain, fix, or optimize any step config from natural language
- **Query Builder AI**: Generate SQL, explain queries, fix errors, natural-language-to-filters
- **Form Designer AI**: Suggest fields from a description with per-field accept/reject
- **Error Diagnosis**: Explain run/step failures with root cause, suggested fixes, corrected config
- **Hybrid KB Steering**: domain-specific knowledge-base files loaded per feature
- **Provider Fallback (M8) / GPT-4 & Claude (F3)**: choose `llama_cpp`, `openai` (GPT-4 presets in Settings), or `anthropic` (Claude) as the primary provider; an optional ordered `AI_FALLBACK_PROVIDERS` chain (e.g. `openai,anthropic,llama_cpp`) is tried on provider errors. LLM-backed `/ai/*` responses carry an `X-AI-Provider` header and `/ai/health` reports every configured provider. Local-only deployments should leave the chain empty so prompts never leave the host

### Security
- **SSRF Protection**: Blocks private/loopback IPs in API calls
- **Webhook Secrets**: HMAC verification for incoming webhooks (fails closed when unset)
- **Role-Based Access**: Admin/Developer/Staff/User permissions
- **Rate Limiting & Brute-Force Protection** (shipped): per-username lockout + per-IP rate limiting on `POST /auth/login`; a shared per-IP sliding-window limiter (`app.services.rate_limiter`, wired via the `require_api_rate_limit` dependency) also bounds request frequency on the high-cost / high-touch routers — `/ai/*` (on top of the per-user AI cost throttle), `/data-query/*` and `/data-export/*` — returning HTTP 429 with a `Retry-After` header when a source IP exceeds the cap. `/data-export/*` uses the alerting variant (`require_export_rate_limit`, G7) so throttled and cap-sized exports notify admins through the configured channels. Limits are env-configurable (`API_REQUESTS_PER_WINDOW`, `API_REQUEST_WINDOW_SECONDS`).
- **Code Sandboxing**: Restricted builtins for custom code steps (subprocess-isolated with CPU/memory limits and a hard timeout)
- **Export Denylist**: CSV export hard-strips sensitive columns (`password_hash`, `ldap_dn`, `custom_data`, tokens, keys) via a secret-column denylist on top of table-level RBAC — prevents bulk-dumping secrets.

### Multi-Tenancy
- **Shared-Schema Isolation**: Every tenant-owned row carries a `tenant_id`; all content queries (workflows, runs, tasks, forms, CMDB, KB, services, schedules, notifications, fields, reports, SQL views, marketplace, email log) are scoped to the caller's tenant at the SQL level
- **Per-Tenant Switching**: Send `X-Tenant-Id` on any request to operate as a member of another tenant; resolved and membership-validated by `get_current_user`, then applied by `scope_current_tenant` — no per-endpoint changes needed
- **Multiple Tenants Per User**: `user_tenants` association table lets a user belong to several tenants while `User.tenant_id` remains their default/primary tenant
- **Tenant Provisioning API**: Admin-only CRUD over `Tenant` records (create/list/get/update) with unique-slug enforcement (409) and not-found (404)
- **Membership Management**: Admin endpoints to list/add/remove a user's membership in a tenant
- **Platform Scope**: Callers with no tenant get an unscoped view; every real user has a non-null `tenant_id` after provisioning
- **UI Tenant Switcher**: The navbar shows a tenant dropdown for users in multiple tenants. Selection is persisted to `localStorage` and sent as the `X-Tenant-Id` header on every request (services/api.ts); switching reloads the page so all open pages re-fetch scoped data. `/auth/me` returns the user's `tenants` and resolved `active_tenant_id`; a stale selection that yields 403 is auto-reset to the default tenant

### Marketplace
- **Publish Workflows**: Export and publish workflows from the detail page with metadata (name, description, category, tags)
- **Publish Nodes**: Save individual step configurations to the marketplace or personal My Nodes library
- **Browse & Search**: Filter by type, category, tags; full-text search; sort by downloads/date/name
- **Install Workflows**: One-click install with configurable options (environment, conflict resolution); delegates to import service
- **Install Nodes**: Returns step payload for designer insert AND saves copy to My Nodes library
- **My Nodes Library**: Personal collection of saved node templates; visible in marketplace and designer panel
- **Security Audit**: Review-before-install panel shows step types, external URLs, custom code, SQL queries, email recipients
- **Downloads Counter**: Tracks install count per item

### CMDB (Configuration Management Database)
- **CI Types**: Define custom types with field schemas (text, select, number, date, boolean, JSON)
- **CI Items**: Create instances of types with structured data; search/filter via Data Explorer
- **Relationships**: Define parent-child and dependency relationships between CIs
- **Dependency Graph**: Visualize CI relationships and impact analysis
- **Bulk Import**: CSV/JSON import for bulk CI creation (backend API)
- **Audit Logging**: Track all CI field changes with before/after values

### Service Catalog & SLA
- **Offerings**: Publish services with descriptions, categories, and entry forms
- **SLA Definitions**: Configure service level agreements with response/resolution targets
- **OLA Tracking**: Internal Operational Level Agreements for backend processes
- **Priority Matrix**: Define priority levels (P1-P4) with color coding and escalation rules

### Forms
- **Form Builder**: Create/read/update/delete forms built from reusable field definitions (`/forms`)
- **Submissions**: Submit form data and manage the submission lifecycle (`/forms/{id}/submit`, `/forms/{id}/submissions`, submission status)
- **Templates**: Reusable form templates; save any form as a template (`/forms/templates`, `/forms/{id}/save-template`)
- **File Uploads**: Upload and download form-associated files (`/forms/upload`, `/forms/download/{filename}`)

### Incident & Change Management
- **Incident Demos**: Sample incidents with severity tracking and resolution workflows
- **Change Demos**: Sample change requests with approval workflows and risk assessment
- **Date Targets**: Configurable deadlines for incident/change resolution with breach alerts

### Knowledge Base
- **Articles**: Store documentation, procedures, and reference material
- **Categorization**: Tag articles by topic for easy discovery
- **Search**: Full-text search across all knowledge base content

### Email Integration
- **IMAP Monitor**: Poll IMAP servers for incoming emails; trigger workflows on match
- **SMTP Configuration**: Admin-configurable SMTP settings with test-email capability
- **Email Steps**: Send emails from workflows with `$input.*` interpolation

### Demo Data
- **Seed Script**: `scripts/demo_seed.py` populates sample workflows, CIs, incidents, and KB articles
- **Reset**: Re-run to refresh demo data without affecting production

### Field Library
- **Field Definitions**: Reusable field schemas shared across forms and CMDB types; full CRUD with deprecation
- **Where-Used**: List every form and CI-type that references a given field
- **Scan**: Audit existing forms/CI-types for field usage
- **Migration Plan**: Generate a migration plan when changing a field definition
- **Data Explorer**: Query any queryable table via a visual filter builder (`POST /data-query/build`) or raw SQL (`POST /data-query/sql`), with field-level RBAC applied

### SQL Views
- **Named Views**: Create/read/update/delete named SQL views; regenerate them from forms/CI-types
- **Admin Management**: List and delete views from the admin panel

### Bulk Operations (Admin)
- Batch deprecate / reactivate / reassign-owner for workflows, forms, and CI-types

### Roles & Field-Level Permissions
- **Roles**: Manage roles and their permissions (`/admin/roles`)
- **Field RBAC**: Per-table visible/editable-field policies; check which fields a role may view or edit (`/admin/role-permissions/visible-fields/{table_name}`, `/admin/role-permissions/editable-fields/{table_name}`, `/admin/role-permissions/check/{table_name}`)

### LDAP
- **Config & Test-Connection**: Configure LDAP and test the bind
- **Sync & Authenticate**: Sync users/groups from LDAP; authenticate against LDAP

### Search, Lookup & Audit
- **Unified Search**: `POST /search` across workflows, forms, and CI items
- **Lookup**: Resolve users (`/lookup/users`) and CI items (`/lookup/ci-items`) by field, or run a custom lookup (`/lookup/perform`)
- **Audit Trails**: Entity-level (`/audit/{entity_type}/{entity_id}`) and user-level (`/audit/user/{user_id}`) audit history

### Data Export
- **Table / Query Export**: Dump a table (`GET /data-export/table/{table}`) or query result (`POST /data-export/query`) to CSV. Developer-scoped, with table-level view RBAC and a hard secret-column denylist (see Export Column Policy below).

### Export Column Policy
CSV export applies **defense in depth** so sensitive fields can never be bulk-dumped:
1. **Table-level RBAC** — both endpoints call `query_security_service.validate_query_access(..., "view")` and return `403` without access (same guard as `/data-query/build`).
2. **Secret-column denylist** — `data_query_service._SECRET_EXPORT_COLUMNS` is the source of truth. `strip_secret_export_columns()` removes any of these even when explicitly requested: `password_hash`, `ldap_dn`, `custom_data`, `refresh_token`, `api_token`, `token`, `secret`, `private_key`, `auth_token`. Applied to both table and query export.
3. **Field-level RBAC** — when a `current_user` is present, per-user visible fields are also applied.
- **Limits**: default `limit` 10,000, hard cap 100,000 (`Query(ge=1, le=100000)`). **Rate limiting**: per-IP sliding-window cap (via `app.services.rate_limiter`) on `/data-export/*` — and `/data-query/*`, `/ai/*` — returns HTTP 429 + `Retry-After` when a source IP exceeds the window (`API_REQUESTS_PER_WINDOW` / `API_REQUEST_WINDOW_SECONDS`).
- **Export Alerting (G7)**: hitting the 100,000-row cap (or an oversized `/data-export/query` limit being clamped to it) and export rate-limit hits emit deduped admin notifications via the configured notification channels (`export_cap_reached` / `export_rate_limited` → email, Slack, signed webhook). Metadata includes only table/limits/row count/user/IP/path — never query filters or values. Alerts are best-effort and never alter the export response. Config: `EXPORT_ALERTS_ENABLED` (default true), `EXPORT_ALERT_COOLDOWN_SECONDS` (default 300).

### Reports
- **Report Builder**: Create/read/update reports and execute them for table/graph output (`/reports`)

### SLA / OLA Stats
- **Stats**: SLA and OLA statistics for services and date targets (`/services/sla-stats`, `/services/ola-stats`)

### Workflow Import / Export
- **Export / Duplicate / Import**: Export a workflow to JSON, duplicate it in the designer, or import from a package/body (`/workflows/{id}/export`, `/workflows/{id}/duplicate`, `/workflows/import`)

### Admin Diagnostics & Lifecycle
- **Hygiene Report**: Data-hygiene report (`GET /admin/hygiene-report`)
- **Logs**: View and export audit logs (`/admin/logs`, `/admin/logs/export`)
- **Promote**: Promote a workflow or form between environments (`/admin/promote/workflow/{id}`, `/admin/promote/form/{id}`)
- **Form Uploads**: Manage uploaded form files (`GET /admin/form-uploads`)
- **Webhook Logs**: Inspect incoming invocations and outgoing delivery attempts/retries (`GET /admin/webhook-logs`, `/admin/webhook-logs/stats`)

### Mobile Admin UI (M7)
- Admin dashboards, runs/tasks tables, modals, and toolbars adapt to phone widths (collapsible nav, scrollable table wrappers, tappable controls). Desktop layouts and behavior are unchanged. An optional CDP smoke check runs at 390×844 (`tests/e2e/mobile-responsive.js`).

### Testing
- **Backend**: 570+ tests (pytest + asyncio) against a dedicated PostgreSQL test database — covering marketplace, engine-behavior regressions, run inspection, and the security-findings regression suite.
- **E2E**: Puppeteer + Chromium headless (CDP-driven) smoke/regression scripts, including a mobile-viewport responsive check (`tests/e2e/mobile-responsive.js`)
- **Regression Net**: Pins current behavior before refactors

## Tech Stack

- **Backend**: Python 3.11+ (developed and tested on 3.13), FastAPI, SQLAlchemy 2.0 (async), Alembic
- **Frontend**: React 18, TypeScript, React Flow, TanStack Query
- **Database**: PostgreSQL 15 only (production and tests; tests use an auto-created `workflow_db_test`). No SQLite fallback exists.
- **AI**: Optional LLM backend. Run locally with `llama.cpp` (no API key), or use `openai` (GPT-4 presets in Settings) / `anthropic` (Claude) via the configurable `AI_PROVIDER` with the matching API key. Optional `AI_FALLBACK_PROVIDERS` adds automatic failover without changing callers.
- **Email**: SMTP (optional, for admin notices + workflow emails)
- **Testing**: pytest, pytest-asyncio, Puppeteer, Docker Compose

## Getting Started

### Prerequisites
- Docker + Docker Compose (v2, `docker compose` syntax)
- PostgreSQL 15 (or use the provided `docker-compose.yml`)
- Python 3.11+

### Quick Start

```bash
# Clone and setup
git clone <repo>
cd PythonWorkflow

# Start services
docker compose up -d

# Run migrations
docker compose exec backend alembic upgrade head

# Run tests
make test-backend    # 570+ collected (see Testing)
make test-e2e        # 18 steps
```

Services:
- Frontend: http://localhost:9000
- Backend API: http://localhost:6000
- API Docs: http://localhost:6000/docs
- Default admin user (created on first run if no users exist): username `admin`, password a high-entropy random `token_urlsafe(18)` (~128 bits) that is logged **once, masked** (`first4****last4`). Change it immediately via `PUT /auth/users/{id}`. The plaintext password is also persisted encrypted-at-rest in the database, so it can be retrieved even if the startup log was never captured:
  - Retrieve it: `python scripts/setup_admin.py --show`
  - Regenerate/reset it: `python scripts/setup_admin.py --reset`

### Local Development

```bash
# Backend
cd backend
pip install -r requirements.txt
python run.py
# API at http://localhost:8000, docs at http://localhost:8000/docs

# Frontend
cd frontend
npm install
npm run dev
# UI at http://localhost:9000
```

### Development

```bash
# Backend (hot-reload)
docker compose up backend

# Frontend
cd frontend && npm install && npm run dev

# E2E tests
make test-e2e
```

## API Endpoints

### Workflows
```
POST   /workflows                    # Create workflow
GET    /workflows                    # List workflows
GET    /workflows/{id}               # Get workflow details
PUT    /workflows/{id}               # Update workflow
DELETE /workflows/{id}               # Delete workflow
POST   /workflows/{id}/run           # Trigger run
```

### Runs
```
GET    /workflows/{workflow_id}/runs                 # List runs (paginated)
GET    /workflows/{workflow_id}/runs/{run_id}        # Get run details
GET    /workflows/{workflow_id}/runs/{run_id}/steps  # Get step instances
DELETE /workflows/{workflow_id}/runs/{run_id}        # Cancel run
```

### Tasks
```
GET    /tasks                        # List tasks (role-filtered, paginated)
GET    /tasks/{id}                   # Get task details
POST   /tasks/{id}/open              # Reopen task
POST   /tasks/{id}/review            # Move to review
POST   /tasks/{id}/take              # Take ownership
POST   /tasks/{id}/complete          # Complete with results (resumes the paused run)
POST   /tasks/{id}/resume            # Resume a paused task (clears pause state)
POST   /tasks/{id}/close             # Close task
POST   /tasks/{id}/reject            # Reject with reason
PUT    /tasks/{id}                   # Update task (admin)
DELETE /tasks/{id}                   # Delete task (admin)
```

### Portal
```
GET    /portal/workflows             # Available workflows (with entry forms)
POST   /portal/workflows/{id}/run    # Run workflow (with form data)
GET    /portal/my-runs               # User's recent runs
GET    /portal/my-tasks              # User's pending tasks
```

### Webhooks
```
POST   /webhook/{workflow_id}        # Trigger via webhook (requires secret)
POST   /api/trigger/{workflow_id}    # External API trigger
GET    /schedules/status             # Active schedule status
```

### Admin
```
GET    /admin/stats                  # Workflow statistics
GET    /admin/runs                   # All workflow runs with node summary
GET    /admin/schedules              # List schedules
POST   /admin/schedules              # Create schedule
PUT    /admin/schedules/:id          # Update schedule
DELETE /admin/schedules/:id          # Delete schedule
POST   /admin/schedules/:id/test     # Test schedule trigger
```

### Tenants
Admin-only provisioning + membership management for shared-schema multi-tenancy. A user may belong to several tenants; send the `X-Tenant-Id` header on any request to operate as a member of another tenant (validated against their membership, then applied to every scoped query).
```
GET    /tenants                        # List tenants (filter: include_inactive)
POST   /tenants                        # Create tenant (unique slug; 409 on collision)
GET    /tenants/{tenant_id}            # Get a single tenant (404 if missing)
PUT    /tenants/{tenant_id}            # Update tenant name / active status
GET    /tenants/{tenant_id}/members    # List members of a tenant
POST   /tenants/{tenant_id}/members    # Add a user to a tenant
DELETE /tenants/{tenant_id}/members/{user_id}  # Remove a user from a tenant
```

### AI Assist
```
POST   /ai/assist-node               # Generate/explain/fix/optimize a workflow node
POST   /ai/assist-query              # Generate/explain/fix SQL for the query builder
POST   /ai/assist-form               # Suggest form fields from a description
POST   /ai/explain-error             # Diagnose workflow run failures
POST   /ai/generate-step             # Generate a single step config from natural language
POST   /ai/generate-workflow         # Generate a whole workflow from a description
POST   /ai/generate-form             # Generate a form from a description
POST   /ai/assist-report             # AI assist for report definitions
POST   /ai/assist-cron               # AI assist for cron/schedule expressions
POST   /ai/assist-webhook            # AI assist for webhook step config
POST   /ai/assist-ci-type            # AI assist for CMDB CI-type definitions
POST   /ai/assist-task               # AI assist for task configuration
POST   /ai/assist-ldap               # AI assist for LDAP configuration
POST   /ai/assist-marketplace        # AI assist for marketplace items
POST   /ai/assist-email-template     # AI assist for email templates
POST   /ai/validate-standards        # Validate against documented standards
GET    /ai/knowledge-base            # Domain KB steering prompts
GET    /ai/health                    # AI service health
```

### Marketplace
```
GET    /marketplace/items            # List items (filter: type, search, category, tag, sort)
GET    /marketplace/items/{id}       # Item detail with author name
POST   /marketplace/items            # Publish workflow or node (Admin/Dev)
PUT    /marketplace/items/{id}       # Update metadata/version (Author/Admin)
DELETE /marketplace/items/{id}       # Delete or archive (Author/Admin)
POST   /marketplace/items/{id}/install  # Install (workflow→import; node→payload+My Nodes)
GET    /marketplace/items/{id}/package    # Raw package content download
POST   /marketplace/items/{id}/preview    # Security audit summary
GET    /marketplace/my-nodes         # List personal node templates
POST   /marketplace/my-nodes         # Save node to personal library
DELETE /marketplace/my-nodes/{id}    # Remove from personal library
GET    /marketplace/categories       # Category catalog + tag cloud
```

### Field Library
```
GET    /field-library                       # List field definitions
POST   /field-library                       # Create a field definition
GET    /field-library/{field_id}            # Get a field definition
PUT    /field-library/{field_id}            # Update a field definition
POST   /field-library/{field_id}/deprecate  # Deprecate a field definition
DELETE /field-library/{field_id}            # Delete a field definition
GET    /field-library/{field_id}/where-used # Forms/CI-types referencing this field
GET    /field-library/scan/forms            # Audit forms for field usage
GET    /field-library/scan/ci-types         # Audit CI-types for field usage
GET    /field-library/migration-plan        # Generate a migration plan for a field
```

### Where-Used (Admin)
```
GET    /admin/where-used/field/{field_id}      # Fields referenced by this field id
GET    /admin/where-used/forms/{field_key}     # Forms using this field key
GET    /admin/where-used/ci-types/{field_key}  # CI-types using this field key
```

### SQL Views
```
GET    /sql-views                    # List views
POST   /sql-views                    # Create a view
PUT    /sql-views/{view_id}          # Update a view
DELETE /sql-views/{view_id}          # Delete a view
GET    /admin/views                  # Admin: list views
POST   /admin/views/regenerate/form/{form_id}      # Regenerate a view from a form
POST   /admin/views/regenerate/ci-type/{ci_type_id}# Regenerate a view from a CI-type
DELETE /admin/views/{view_name}      # Admin: delete a view
```

### Data Explorer & Data Fields
```
GET    /data-query/tables            # Queryable tables
POST   /data-query/build             # Visual filter-builder query (field-level RBAC)
POST   /data-query/sql               # Raw SQL query (field-level RBAC)
PUT    /data-query/records/{table_name}/{record_id}/custom-data
POST   /data-query/bulk-update/custom-data
GET    /data-fields                  # List data field definitions
POST   /data-fields                  # Create a data field definition
GET    /data-fields/{field_id}       # Get a data field definition
PUT    /data-fields/{field_id}       # Update a data field definition
DELETE /data-fields/{field_id}       # Delete a data field definition
```

### LDAP
```
GET    /admin/ldap/config            # Get LDAP config
PUT    /admin/ldap/config            # Update LDAP config
POST   /admin/ldap/test-connection   # Test the LDAP connection
POST   /admin/ldap/sync              # Sync users/groups from LDAP
POST   /admin/ldap/authenticate      # Authenticate against LDAP
```

### Search, Lookup & Audit
```
GET    /search                       # Unified search (workflows/forms/CI items)
GET    /lookup/users                 # Resolve users by field
GET    /lookup/ci-items              # Resolve CI items by field
POST   /lookup/perform               # Custom lookup
GET    /audit/{entity_type}/{entity_id}      # Entity-level audit trail
GET    /audit/user/{user_id}         # User-level audit trail
```

### Data Export
```
GET    /data-export/table/{table_name}  # Dump a table to CSV (secret columns stripped, RBAC)
POST   /data-export/query            # Export a query result to CSV
```

### Reports
```
GET    /reports                      # List reports
GET    /reports/{report_id}          # Get a report
POST   /reports                      # Create a report
PUT    /reports/{report_id}          # Update a report
POST   /reports/{report_id}/execute  # Execute a report (table/graph)
DELETE /reports/{report_id}          # Delete a report
```

### Roles & Field-Level Permissions
```
GET    /admin/roles                   # List roles
POST   /admin/roles                   # Create a role
GET    /admin/roles/{role_id}         # Get a role
PUT    /admin/roles/{role_id}         # Update a role
DELETE /admin/roles/{role_id}         # Delete a role
GET    /admin/role-permissions        # List role-permission policies
POST   /admin/role-permissions        # Create a role-permission policy
PUT    /admin/role-permissions/{permission_id}
DELETE /admin/role-permissions/{permission_id}
GET    /admin/role-permissions/check/{table_name}          # Can this role view/edit this table?
GET    /admin/role-permissions/visible-fields/{table_name} # Fields the role can view
GET    /admin/role-permissions/editable-fields/{table_name}# Fields the role can edit
```

### Bulk Operations (Admin)
```
POST   /bulk/workflows/deprecate      # Batch-deprecate workflows
POST   /bulk/workflows/reactivate     # Batch-reactivate workflows
POST   /bulk/workflows/reassign-owner # Batch-reassign workflow owners
POST   /bulk/forms/deprecate          # Batch-deprecate forms
POST   /bulk/forms/reactivate         # Batch-reactivate forms
POST   /bulk/ci-types/deprecate       # Batch-deprecate CI-types
POST   /bulk/ci-types/reactivate      # Batch-reactivate CI-types
```

### Branding & Portal Customization
```
GET    /branding                     # Get branding (system name, logo)
PUT    /settings/branding            # Update branding
GET    /settings/banner              # Get portal banner
PUT    /settings/banner              # Update portal banner
GET    /portal/banner                # Effective portal banner (client-side)
GET    /settings/priority-matrix     # Priority matrix (admin)
PUT    /settings/priority-matrix     # Update priority matrix
GET    /portal/priority-matrix       # Priority matrix (portal-facing)
```

### SLA / OLA Stats
```
GET    /services/sla-stats           # SLA statistics
GET    /services/ola-stats           # OLA statistics
```

### Admin Diagnostics & Lifecycle
```
GET    /admin/hygiene-report         # Data-hygiene report
GET    /admin/logs                   # View audit logs
GET    /admin/logs/export            # Export audit logs
POST   /admin/promote/workflow/{workflow_id}   # Promote a workflow across environments
POST   /admin/promote/form/{form_id}           # Promote a form across environments
GET    /admin/form-uploads           # Manage uploaded form files
```

### CMDB Extras
```
GET    /cmdb/items/export            # Export CI items
GET    /cmdb/items/{item_id}/history # CI item field-change history
POST   /cmdb/types/{type_id}/webhook     # Per-CI-type webhook config
GET    /cmdb/types/{type_id}/webhook     # Get per-CI-type webhook config
GET    /cmdb/templates                   # CI item templates
POST   /cmdb/templates/{template_key}/apply  # Apply a CI item template
GET    /cmdb/stats                   # CMDB statistics
GET    /cmdb/search                  # Search CI items
GET    /cmdb/items/{item_id}/graph   # Dependency graph for a CI item
```

## Configuration

### Environment Variables
```bash
# Database (PostgreSQL only)
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db

# Test database (used by make test-backend; auto-created if missing).
# Provide real credentials via your environment/secret manager, e.g.:
#   TEST_DATABASE_URL=postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@postgres:5432/workflow_db_test
TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/workflow_db_test

# SMTP (optional, for admin notices + email steps)
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=user
SMTP_PASSWORD=pass
SMTP_FROM=noreply@example.com
ADMIN_NOTIFY_EMAIL=admin@example.com

# Webhook secret (optional)
WEBHOOK_SECRET=your-secret-here

# AI service (optional)
AI_PROVIDER=llama_cpp
AI_FALLBACK_PROVIDERS=
LLAMA_CPP_URL=http://localhost:8081
LLAMA_CPP_MODEL=default
# Cloud alternatives (GPT-4 or Claude); see .env.example
# OPENAI_API_KEY=
# OPENAI_MODEL=gpt-4o
# ANTHROPIC_API_KEY=
# ANTHROPIC_MODEL=claude-sonnet-5-5
```

See `.env.example` for the full list.

## Project Structure

```
PythonWorkflow/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI routers
│   │   ├── core/             # Config, database, security
│   │   ├── middleware/       # Request middleware (multi-tenant `X-Tenant-Id` resolution)
│   │   ├── models/           # SQLAlchemy models
│   │   ├── schemas/          # Pydantic schemas
│   │   ├── data/             # Demo workflow packages
│   │   └── services/         # Business logic
│   ├── alembic/              # Database migrations
│   ├── tests/                # Backend tests (PostgreSQL, see tests/conftest.py)
│   └── pytest.ini
├── frontend/
│   └── src/
│       ├── components/       # React components
│       ├── pages/            # Page components
│       └── services/         # API client
├── knowledge-base/           # AI steering prompts + templates (mounted into backend container)
├── scripts/                  # Admin utilities (setup_admin, demo seeding)
├── tests/e2e/                # E2E test scripts (Puppeteer)
├── docs/                     # Per-feature plans + session logs
├── .env.example              # Environment variable reference
└── docker-compose.yml
```

## Development Phases (Completed)

- ✅ **Phase 0**: Foundations (test baseline, alembic, e2e harness, regression net)
- ✅ **Phase 1**: Engine correctness (condition contract, strict errors, Model B, unified execution, state machine, timeout/retries/hooks)
- ✅ **Phase 2**: Real executors (Email, DB Query, Form, Custom Code/Webhook, Webhooks router, Scheduler)
- ✅ **Phase 3**: Human-in-the-loop (Designer nodes, task lifecycle, Portal entry forms + tasks)
- ✅ **Phase 4**: Designer & UI (Remove dead field, full node palette, Run monitor enhancements)
- ✅ **Phase 5**: Feature gaps (Calculation, AI condition, Report/Form, Step templates, Programmable delay)
- ✅ **Phase 6**: Hardening (SSRF protection, pagination, docs, dead-code sweep)
- ✅ **AI Assist**: Hybrid KB steering, backend AI endpoints, per-node/query/form/error AI assist (all 6 phases)
- ✅ **Phase 10**: Internal Marketplace — publish/discover/install workflows and node templates; My Nodes library; security audit preview; demo migration
- ✅ **Multi-Tenancy**: Shared-schema tenant isolation, per-request tenant switching via `X-Tenant-Id`, multiple tenants per user (`user_tenants`), admin tenant provisioning + membership API, active-tenant query scoping

See `docs/` for reference documentation (`docker-deployment.md`, `scheduling.md`, `entry-forms-and-tasks.md`) and the active plan (`incident-change-plan.md`). Completed feature plans are removed once shipped; notable history lives in `CHANGELOG.md`.

## Task System

The workflow engine supports human-in-the-loop execution through `human_task` and `approval` step types. When a workflow reaches one of these steps, it:

1. **Creates a task** assigned to a user or group
2. **Pauses execution** until the task is completed
3. **Resumes** automatically when the task is marked complete

### Task Lifecycle

Tasks follow this status flow:
- **open** → Task created, awaiting assignment
- **review** → Task reviewed by another user
- **owned** → User has taken ownership
- **completed** → Task work finished with results
- **closed** → Task finalized (admin/developer/staff only)

### Step Enable/Disable

Workflow steps have an `is_enabled` flag:
- **Enabled**: Steps execute normally during workflow runs
- **Disabled**: Steps are skipped (marked as "skipped" in step_instances), but workflow continues to connected next steps

This allows temporarily disabling parts of a workflow without deleting them or breaking connections.

### Roles & Permissions

| Role | Workflow Access | Task Access | Portal Access |
|------|----------------|-------------|---------------|
| **Admin** | Full CRUD, all environments | All tasks, can reopen/close any | Full access |
| **Developer** | Create/edit workflows and forms | Own tasks + group tasks (closed hidden by default) | Full access |
| **Staff** | View workflows | Own tasks + group tasks (closed hidden by default), spawn based on group membership | Spawn workflows based on group membership |
| **User** | View published workflows | Own tasks only (closed hidden by default), spawn based on group membership | Spawn workflows based on group membership |

### Task Dashboard

- **Admin**: `/admin/tasks` — view all tasks, filter by status, complete/close
- **Developer/Staff**: `/tasks` — view own + group tasks, take ownership, complete
- **User**: `/my-tasks` — view assigned tasks, complete with results

## Submission Portal

The portal provides a user-friendly interface for discovering and running workflows:

- **Workflow Cards**: Displayed with icons, descriptions, and environment badges
- **Run Button**: One-click workflow execution
- **My Runs**: Track recently started workflows
- **Group-Based Access**: Staff/users can only run workflows their groups have permission to access

## License

Distributed under the terms of the Apache License 2.0. This project is open source and available for use and modification. See LICENSE for details.

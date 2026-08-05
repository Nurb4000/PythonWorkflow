# Python Workflow System - Design Document

## Overview
A web-based workflow management system with AI-generated steps, scheduling, and form design capabilities. Built with Python backend and modern web frontend.

## Architecture

### Core Components

1. **Workflow Engine**
   - Orchestrates step execution
   - Manages state and data flow between steps
   - Handles conditional branching and error recovery

2. **AI Integration Layer**
   - llama.cpp server (in-house) for step generation
   - Knowledge base with prompts/templates
   - Generates structured step definitions (JSON/YAML)

3. **Form Designer**
   - Visual drag-and-drop interface
   - AI-assisted form schema generation
   - JSON Schema → UI rendering

4. **Scheduler**
   - Cron-based workflow triggering
   - Manual trigger via web UI
   - External API triggers

5. **Admin Dashboard**
    - Workflow monitoring and reporting
    - Query tools for execution data
    - User management

6. **Workflow Import/Export**
    - Export workflows with all dependencies as XML or JSON
    - Import with conflict resolution and ID remapping
    - Duplicate workflows within the same system
    - Demo/training workflow packages

### Tech Stack

**Backend:**
- Python 3.11+
- FastAPI (web framework)
- SQLAlchemy (ORM) with asyncpg
- PostgreSQL (database)
- APScheduler (task scheduling)

**Frontend:**
- React + TypeScript (GUI)
- React Flow (workflow designer)
- JSON Schema Form libraries (form designer)
- CustomFieldsEditor (reusable dynamic field renderer)

**AI:**
- llama.cpp server (local LLM inference)
- Custom prompts and knowledge base
- Structured output validation

## Database Schema (Core Tables)

```
workflows
  - id, name, description, version, created_at, updated_at

workflow_steps
  - id, workflow_id, step_type, definition (JSON), position, condition_expr

workflow_runs
  - id, workflow_id, status (pending/running/completed/failed), triggered_by, started_at, completed_at

step_instances
  - id, workflow_run_id, step_id, status, input_data (JSON), output_data (JSON), error_msg

schedules
  - id, workflow_id, cron_expr, enabled, last_run, next_run

forms
  - id, name, schema (JSON), version, created_by

form_submissions
  - id, form_id, submitted_by, data (JSON), submitted_at
```

## API Endpoints

### Workflows
- `POST /api/workflows` - Create workflow
- `GET /api/workflows` - List workflows (supports `search`, `status`, `sort_by`, `sort_order` query params)
- `GET /api/workflows/{id}` - Get workflow details
- `PUT /api/workflows/{id}` - Update workflow
- `DELETE /api/workflows/{id}` - Delete workflow

**Workflow list filters:**
| Param | Values | Description |
|-------|--------|-------------|
| `search` | any string | Case-insensitive ILIKE on name and description |
| `status` | `active`, `inactive`, `published`, `draft` | Filter by workflow state |
| `sort_by` | `name`, `created_at`, `runs_count`, `steps_count`, `portal_order` | Sort field (default: `name`) |
| `sort_order` | `asc`, `desc` | Sort direction (default: `asc`) |

### Workflow Runs
- `POST /api/workflows/{id}/run` - Trigger workflow
- `GET /api/workflows/{id}/runs` - List runs
- `GET /api/workflows/{id}/runs/{run_id}` - Get run details
- `GET /api/workflows/{id}/runs/{run_id}/steps` - Get step instances

### AI Generation
- `POST /api/ai/generate-step` - Generate step from description
- `POST /api/ai/generate-form` - Generate form schema

### Forms
- `POST /api/forms` - Create form
- `GET /api/forms/{id}` - Get form schema

### Tasks
- `GET /api/tasks` - List tasks (role-filtered)
- `GET /api/tasks/:id` - Get task details
- `POST /api/tasks/:id/open` - Reopen closed task (admin)
- `POST /api/tasks/:id/review` - Move to review status
- `POST /api/tasks/:id/take` - Take ownership
- `POST /api/tasks/:id/complete` - Complete task with results
- `POST /api/tasks/:id/close` - Close completed task
- `POST /api/tasks/:id/reject` - Reject task with reason
- `PUT /api/tasks/:id` - Update task (admin)
- `DELETE /api/tasks/:id` - Delete task (admin)

### Portal
- `GET /api/portal/workflows` - List available workflows (published + active)
- `POST /api/portal/workflows/:id/run` - Run a workflow
- `GET /api/portal/my-runs` - Get user's recent runs

### Admin
- `GET /api/admin/stats` - Workflow statistics
- `GET /api/admin/runs` - All workflow runs with node summary
- `GET /api/admin/schedules` - List schedules
- `POST /api/admin/schedules` - Create schedule
- `PUT /api/admin/schedules/:id` - Update schedule
- `DELETE /api/admin/schedules/:id` - Delete schedule
- `POST /api/admin/schedules/:id/test` - Test schedule trigger

### Branding
- `GET /api/branding` - Get branding settings (public)
- `GET /api/branding/logo` - Get logo URL (public)
- `PUT /api/settings/branding` - Update branding (admin)
- `POST /api/settings/branding/logo` - Upload logo (admin)
- `POST /api/forms/{id}/submit` - Submit form data

### Admin/Reports
- `GET /api/admin/runs` - List all runs with filters
- `GET /api/admin/stats` - Workflow execution statistics
- `GET /api/admin/workflows/{id}/audit-log` - Detailed audit trail

## Database

PostgreSQL is the only supported database. The connection is configured via the `DATABASE_URL` environment variable.

## Workflow Step Types

### Built-in Steps
1. **API Call** - HTTP requests with configurable methods, headers, auth
2. **Database Query** - SQL or ORM operations
3. **Email** - Send notifications with templates
4. **Form Collection** - Display and collect form data
5. **Condition** - Branch based on variables
6. **Delay/Sleep** - Wait before next step
7. **Webhook** - Listen for external callbacks
8. **Custom Code** - Execute Python snippets (sandboxed)
9. **Report** - Render data as table/graph/read-only form, or execute SQL queries directly

### AI-Generated Steps
- Natural language description → structured step definition
- Validated against schema before execution
- Can reference knowledge base for best practices

## Form Designer Workflow

1. Admin describes form needs to AI ("contact form with name, email, phone")
2. AI generates JSON Schema
3. Form designer renders preview
4. Admin adjusts layout/fields visually
5. Save as template or workflow step
6. Forms can be embedded in workflows or used standalone

### Field Sources
- **New Field** — field data lives only in the form submission (default)
- **Reference Existing** — field references a column on another database table; edits save back to that table on submission. The target record ID is resolved from workflow context (`__ref_{field_name}` in submission data).

### Custom Fields Integration
Admin/developer forms (User Management, Group Management, etc.) can embed `<CustomFieldsEditor targetTable="table_name" />` to automatically render any custom fields defined for that table via Field Manager. Values are merged into the record's `custom_data` JSON column on save.

## Report Node

The report step type supports multiple data sources:

### Report Types
- **Table** — display data from a preceding step as a table
- **Graph/Chart** — visualize data from a preceding step
- **Read-only Form** — display form data in read-only mode
- **SQL Query** — execute a raw SELECT query against the database

### SQL Query Mode
- Free-form SQL textarea with `$input.field` interpolation for upstream data
- Row limit control (1–10,000)
- Safety: SELECT-only, keyword blacklist prevents DML/DDL
- Output: `{ columns[], rows[], row_count, executed_at }` passed to downstream steps

## Security Considerations

- Authentication: JWT or session-based
- Authorization: Role-based (admin, user, viewer)
- API keys for external integrations
- Sandboxed execution for custom code steps
- Audit logging for all actions
- Encrypted secrets for credentials

## Development Phases (All Complete)

### Phase 0: Foundations ✅
- P0.1: Backend test baseline (pytest + asyncio + SQLite)
- P0.2: Alembic migrations
- P0.3: E2E test harness (Puppeteer + Chromium)
- P0.4: Regression net (engine/executor unit tests)

### Phase 1: Engine Correctness ✅
- P1.1: Condition contract (Model B: routes[] + default_target_step_id)
- P1.2: Strict errors + admin notices via SMTP
- P1.3: AI + templates emit Model B shape
- P1.4: Unify linear vs graph execution (single traversal)
- P1.5: Run state machine + resume (waiting status, no replay)
- P1.6: Run timeout, per-step retries, failure hooks

### Phase 2: Real Executors & Triggers ✅
- P2.1: Real EmailExecutor ($input.* interpolation)
- P2.2: Real DatabaseQueryExecutor (parameterized queries)
- P2.3: Real FormExecutor (pull submission data)
- P2.4: Register custom_code + webhook executors
- P2.5: Register webhooks router with secret verification
- P2.6: Scheduler runs use P1.5 state path

### Phase 3: Human-in-the-Loop ✅
- P3.1: Designer nodes + editor for human_task / approval
- P3.2: Task lifecycle correctness (approve/reject → resume)
- P3.3: Portal entry form + auto-surface open tasks

### Phase 4: Designer & UI Correctness ✅
- P4.1: Remove dead "Condition Expression" field
- P4.2: Full node palette (12 step types with editors)
- P4.3: Run monitor (chosen branch, per-step outputs/errors)

### Phase 5: Feature Gaps ✅
- P5.1: Calculation node (safe eval)
- P5.2: AI condition node
- P5.3: Read-only form + report nodes (table, graph, read-only form, SQL query)
- P5.4: Step templates via template_service
- P5.5: Programmable delay / SQL-wait

### Phase 6: Hardening ✅
- P6.1: Security (SSRF protection, eval boundaries, webhook auth)
- P6.2: Performance (pagination on runs/tasks)
- P6.3: Docs (README, TESTING_GUIDE, DESIGN.md updated)
- P6.4: Dead-code sweep (clean up stubs, remove unused paths)
- User management

### Phase 6: Form Designer
- Visual form builder
- AI-assisted form creation
- Form templates
- Submission tracking
- Cross-table field references (edit + save-back to source table)
- URL-driven edit mode (`/forms?editing=1`)

### Phase 7: Custom Fields & Dynamic Forms
- Universal CustomFieldsEditor component for any admin/dev create/edit form
- Custom data persisted on user create/edit via `custom_data` JSON column
- Field Manager for defining custom fields on any queryable table
- Data Explorer for querying tables with custom field support

### Phase 8: SQL Views & Advanced Reporting
- SQL View Manager for creating named database views (admin/developer)
- Views simplify complex queries in report nodes and Data Explorer
- Report nodes support raw SQL execution with `$input.field` interpolation
- Views are synced on application startup, dropped on deletion

## Project Structure

```
PythonWorkflow/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   ├── models/
│   │   ├── services/
│   │   │   ├── workflow_engine.py
│   │   │   ├── ai_generator.py
│   │   │   └── scheduler.py
│   │   └── utils/
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   └── services/
│   └── package.json
├── knowledge-base/
│   ├── prompts/
│   └── templates/
├── scripts/
└── README.md
```

## Current Progress

### Phase 1: Core Engine ✅ COMPLETE
- [x] FastAPI project structure
- [x] Database models (SQLAlchemy)
- [x] Workflow engine with step execution
- [x] Step executors (API, DB, Email, Condition, Delay)
- [x] API endpoints for workflows and runs
- [x] Admin endpoints for monitoring
- [x] AI integration service (llama.cpp)
- [x] Scheduler service (APScheduler)
- [x] PostgreSQL database integration

### Phase 2: Web UI ✅ COMPLETE
- [x] React + Vite + TypeScript setup
- [x] React Flow for visual workflow designer
- [x] API service layer (axios)
- [x] Workflow list page with CRUD, search, filter (status), and sort controls
- [x] Workflow detail page with run history
- [x] Visual workflow designer (React Flow)
- [x] Run monitor with step instances
- [x] Admin dashboard with stats and filters
- [x] Responsive CSS styling

### Phase 3: AI Integration Enhancement ✅ COMPLETE
- [x] Knowledge base with prompts and templates
- [x] AI service with validation and context
- [x] Workflow generation from templates
- [x] Template management service
- [x] Enhanced AI endpoints (generate-workflow, knowledge-base)
- [x] Unit tests for workflow engine and AI service
- [x] Step type validation
- [x] Form schema validation

### Phase 4: Scheduling & Triggers ✅ COMPLETE
- [x] Enhanced scheduler with webhook support
- [x] External API trigger endpoint
- [x] Cron expression validation
- [x] Schedule management (CRUD + test)
- [x] Webhook trigger endpoint
- [x] Frontend schedule manager component
- [x] Admin dashboard integration
- [x] Scheduling documentation

### Phase 5: User Management & Access Control ✅ COMPLETE
- [x] User authentication models (User, Group, APIToken)
- [x] Role-based access control (admin, developer, staff, user)
- [x] Authentication service with JWT tokens
- [x] Password hashing with bcrypt
- [x] Login/register endpoints
- [x] User management (CRUD, role updates)
- [x] Group management for organizing users and workflow permissions
- [x] API token generation
- [x] Portal endpoints for user/staff workflow access
- [x] Workflow permission checking by group
- [x] Frontend authentication context and components
- [x] Login/Register forms
- [x] User Management admin page
- [x] Protected routes with role-based access

### Phase 6: Form Designer ✅ COMPLETE
- [x] Form models (Form, FormSubmission, FormTemplate)
- [x] Form service with validation
- [x] Form CRUD endpoints
- [x] Form submission handling
- [x] Form template management
- [x] Schema validation (required fields, types)
- [x] Frontend FormDesigner component
- [x] FormRenderer component for displaying forms
- [x] Integration with workflow steps
- [x] Navigation and routing
- [x] Cross-table field references (edit + save-back)
- [x] URL-driven edit mode (`/forms?editing=1`)
- [x] Field editor labels (Field Name, Display Title, Description)
- [x] Publish/unpublish toggle (matches workflow behavior)

### Phase 7: Custom Fields & Dynamic Forms ✅ COMPLETE
- [x] CustomFieldsEditor reusable component
- [x] Universal custom field support on admin/dev forms
- [x] User Management create/edit with custom fields
- [x] Backend custom_data persistence (create_user, update_user)
- [x] Field Manager for defining custom fields on any table
- [x] Data Explorer with custom field filtering

### Phase 7: Task System & Role-Based Dashboards ✅ COMPLETE
- [x] Task model with status lifecycle (open → review → owned → completed → closed)
- [x] Human-task and approval step types in workflow engine
- [x] Workflow pause/resume on task completion
- [x] Task API endpoints (CRUD + lifecycle actions)
- [x] Role-based task filtering (admin=all, dev/staff=own+group, user=own)
- [x] Admin task dashboard with status tabs and column config
- [x] Developer/Staff task dashboard (closed tasks hidden by default)
- [x] User task dashboard (/my-tasks)
- [x] Task detail page with take/complete/reject/close actions
- [x] Portal workflow spawning with group-based permissions
- [x] Admin runs endpoint with node summary and search
- [x] Column customization and CSV export for all dashboards
- [x] Branding system (logo, system name, portal name) - fixed JSON body support
- [x] Admin auth gate on all admin endpoints
- [x] Step enable/disable flag (is_enabled) - disabled steps are skipped during execution

### Phase 8: SQL Views & Advanced Reporting ✅ COMPLETE
- [x] SQL View Manager page with CRUD operations
- [x] Backend service for view lifecycle management
- [x] View sync on application startup
- [x] Safety validation (CREATE VIEW only, keyword blacklist)
- [x] Report node SQL query execution with $input interpolation
- [x] Database session passed to all step executors

### Phase 9: Workflow Import/Export ✅ COMPLETE
- [x] Export workflow + dependencies as XML or JSON
- [x] Import with conflict resolution (copy/skip/overwrite)
- [x] Duplicate workflow within same system
- [x] Demo/training workflow packages (5 examples)
- [x] ID remapping with symbolic refIds
- [x] User matching by email on import

## Database Schema (Core Tables)

```
workflows
  - id, name, description, version, is_active, is_published, environment, config (JSON), 
    portal_icon, portal_order, portal_visible, created_at, updated_at

workflow_steps
  - id, workflow_id, step_type (api_call, database_query, email, form, condition, delay, 
    webhook, custom_code, human_task, approval), definition (JSON), position, 
    condition_expr, is_enabled, created_at

workflow_runs
  - id, workflow_id, status (pending/running/completed/failed/cancelled), triggered_by, 
    input_data (JSON), output_data (JSON), error_message, started_at, completed_at, created_at

step_instances
  - id, workflow_run_id, step_id, status (pending/running/completed/failed/skipped), 
    input_data (JSON), output_data (JSON), error_message, started_at, completed_at, position

tasks
  - id, workflow_run_id, step_id, title, description, status (open/review/owned/completed/closed),
    assigned_to_user_id, assigned_group_id, form_id, task_data (JSON), result_data (JSON),
    created_at, updated_at, completed_at, closed_at

schedules
  - id, workflow_id, cron_expression, is_enabled, last_run_at, next_run_at, created_at, updated_at

forms
  - id, name, description, schema (JSON), version, created_by, is_published, environment, 
    portal_icon, portal_order, portal_visible, created_at, updated_at

form_submissions
  - id, form_id, submitted_by, data (JSON), submitted_at

users
  - id, username, email, password_hash, full_name, role (admin/developer/staff/user), 
    is_active, is_verified, custom_data (JSON), created_at, updated_at

groups
  - id, name, description, is_active, custom_data (JSON), created_at, updated_at

custom_field_definitions
  - id, field_key, label, field_type, target_table, scope, scope_id, config (JSON), 
    is_required, is_active, created_by, created_at, updated_at

user_groups (junction)
  - user_id, group_id

workflow_permissions (junction)
  - workflow_id, group_id

system_settings (key-value store for branding)
  - key, value, updated_at

sql_views
  - id, name, description, definition_sql, is_active, created_by, created_at, updated_at
```

## Deployment

### Docker (Recommended)
```bash
# Start all services
docker compose up --build

# Backend: http://localhost:6000
# Frontend: http://localhost:9000
# API Docs: http://localhost:6000/docs
```

See `docs/docker-deployment.md` for detailed Docker setup and production deployment.

## Next Steps

1. **Testing**: Run the application and test all features (in progress)
2. **Documentation**: ✅ Complete API documentation
3. **Deployment**: Set up production environment
4. **Monitoring**: Add logging and monitoring
5. **Enhancements**: 
   - Approval workflow with reject/revise cycles
   - Task notifications (email/in-app)
   - Bulk task operations
   - Task templates
   - Advanced filtering and sorting on dashboards

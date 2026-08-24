# Python Workflow System

A production-ready workflow automation platform with visual designer, AI-assisted step generation, human-in-the-loop execution, and comprehensive task management.

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

## Features

### Core Engine
- **Visual Workflow Designer**: Drag-and-drop interface with graph-mode execution
- **Condition Routing**: Model B condition steps with per-route expressions and default targets
- **Parallel Execution**: Graph-mode workflows support fan-out/fan-in with visited-set deduplication
- **State Machine**: Runs track status (pending/running/completed/failed/waiting/timeout/cancelled)
- **Resume Support**: Human-task pauses allow workflow resumption without re-execution
- **Timeout & Retries**: Configurable run timeouts and per-step retry logic
- **Failure Hooks**: HTTP callbacks on step/run failure

### Executors (13 types)
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

### Security
- **SSRF Protection**: Blocks private/loopback IPs in API calls
- **Webhook Secrets**: HMAC verification for incoming webhooks
- **Role-Based Access**: Admin/Developer/Staff/User permissions
- **Code Sandboxing**: Restricted builtins for custom code steps

### Marketplace
- **Publish Workflows**: Export and publish workflows from the detail page with metadata (name, description, category, tags)
- **Publish Nodes**: Save individual step configurations to the marketplace or personal My Nodes library
- **Browse & Search**: Filter by type, category, tags; full-text search; sort by downloads/date/name
- **Install Workflows**: One-click install with configurable options (environment, conflict resolution); delegates to import service
- **Install Nodes**: Returns step payload for designer insert AND saves copy to My Nodes library
- **My Nodes Library**: Personal collection of saved node templates; visible in marketplace and designer panel
- **Security Audit**: Review-before-install panel shows step types, external URLs, custom code, SQL queries, email recipients
- **Downloads Counter**: Tracks install count per item

### Testing
- **Backend**: 141 tests (pytest + asyncio) run against a dedicated PostgreSQL test database — includes marketplace, engine-behavior regression net, and run-inspector suites
- **E2E**: 10 tests (Puppeteer + Chromium headless)
- **Regression Net**: Pins current behavior before refactors

## Tech Stack

- **Backend**: Python 3.11, FastAPI, SQLAlchemy 2.0 (async), Alembic
- **Frontend**: React 18, TypeScript, React Flow, TanStack Query
- **Database**: PostgreSQL 15 (production and tests; tests use an auto-created `workflow_db_test`)
- **AI**: llama.cpp (optional, for step generation)
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
make test-backend    # 141/141 passing
make test-e2e        # 10/10 passing
```

Services:
- Frontend: http://localhost:9000
- Backend API: http://localhost:6000
- API Docs: http://localhost:6000/docs
- Default admin login (created on first run): `admin` / `admin123`

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
GET    /workflows/{id}/runs          # List runs (paginated)
GET    /runs/{id}                    # Get run details
GET    /runs/{id}/steps              # Get step instances
DELETE /runs/{id}                    # Cancel run
POST   /runs/{id}/resume             # Resume paused run
```

### Tasks
```
GET    /tasks                        # List tasks (role-filtered, paginated)
GET    /tasks/{id}                   # Get task details
POST   /tasks/{id}/open              # Reopen task
POST   /tasks/{id}/review            # Move to review
POST   /tasks/{id}/take              # Take ownership
POST   /tasks/{id}/complete          # Complete with results
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

### AI Assist
```
POST   /ai/assist-node               # Generate/explain/fix/optimize a workflow node
POST   /ai/assist-query              # Generate/explain/fix SQL for the query builder
POST   /ai/assist-form               # Suggest form fields from a description
POST   /ai/explain-error             # Diagnose workflow run failures
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

## Configuration

### Environment Variables
```bash
# Database (PostgreSQL only)
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db

# Test database (used by make test-backend; auto-created if missing)
TEST_DATABASE_URL=postgresql+asyncpg://workflow_user:workflow_password@postgres:5432/workflow_db_test

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
LLAMA_CPP_URL=http://localhost:8081
LLAMA_CPP_MODEL=default
```

See `.env.example` for the full list.

## Project Structure

```
PythonWorkflow/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI routers
│   │   ├── core/             # Config, database, security
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

## Next Steps

- **P7**: Production deployment hardening (secrets management, rate limiting, audit logging)
- **P8**: Advanced features (sub-workflows, parallel branches with synchronization, error handling patterns)
- **P9**: Performance optimization (connection pooling, query optimization, caching)

See `docs/` for reference documentation (`docker-deployment.md`, `scheduling.md`, `ENTRY_FORMS_AND_TASKS.md`) and the active plan (`INCIDENT_CHANGE_PLAN.md`). Completed feature plans are removed once shipped; notable history lives in `CHANGELOG.md`.

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

Private project

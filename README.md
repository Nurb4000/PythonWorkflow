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

### Executors (12 types)
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

### Security
- **SSRF Protection**: Blocks private/loopback IPs in API calls
- **Webhook Secrets**: HMAC verification for incoming webhooks
- **Role-Based Access**: Admin/Developer/Staff/User permissions
- **Code Sandboxing**: Restricted builtins for custom code steps

### Testing
- **Backend**: 76 tests (pytest + asyncio + SQLite in-memory)
- **E2E**: 10 tests (Puppeteer + Chromium headless)
- **Regression Net**: Pins current behavior before refactors

## Tech Stack

- **Backend**: Python 3.11, FastAPI, SQLAlchemy 2.0 (async), Alembic
- **Frontend**: React 18, TypeScript, React Flow, TanStack Query
- **Database**: PostgreSQL 15 (production), SQLite (tests)
- **AI**: llama.cpp (optional, for step generation)
- **Email**: SMTP (optional, for admin notices + workflow emails)
- **Testing**: pytest, pytest-asyncio, Puppeteer, Docker Compose

## Getting Started

### Prerequisites
- Docker + Docker Compose
- PostgreSQL 15 (or use provided docker-compose)
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
make test-backend    # 76/76 passing
make test-e2e        # 10/10 passing
```

### Development

```bash
# Backend (hot-reload)
docker compose up backend

# Frontend
cd frontend && npm install && npm start

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

## Configuration

### Environment Variables
```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db

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

## Project Structure

```
PythonWorkflow/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI routers
│   │   ├── core/             # Config, database, security
│   │   ├── models/           # SQLAlchemy models
│   │   ├── schemas/          # Pydantic schemas
│   │   └── services/         # Business logic
│   ├── alembic/              # Database migrations
│   ├── tests/                # Backend tests
│   └── pytest.ini
├── frontend/
│   └── src/
│       ├── components/       # React components
│       ├── pages/            # Page components
│       └── services/         # API client
├── knowledge-base/           # AI prompts + templates
├── tests/e2e/                # E2E test scripts
├── docs/
│   └── REPAIR_PLAN.md        # Development plan + session log
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

## Next Steps

- **P7**: Production deployment hardening (secrets management, rate limiting, audit logging)
- **P8**: Advanced features (sub-workflows, parallel branches with synchronization, error handling patterns)
- **P9**: Performance optimization (connection pooling, query optimization, caching)

See `docs/REPAIR_PLAN.md` for detailed session logs and progress tracking.

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

## API Endpoints

### Task Endpoints

```
GET    /tasks                    # List tasks (role-filtered)
GET    /tasks/:id                # Get task details
POST   /tasks/:id/open           # Reopen closed task (admin)
POST   /tasks/:id/review         # Move to review status
POST   /tasks/:id/take           # Take ownership
POST   /tasks/:id/complete       # Complete task with results
POST   /tasks/:id/close          # Close completed task
POST   /tasks/:id/reject         # Reject task with reason
PUT    /tasks/:id                # Update task (admin)
DELETE /tasks/:id                # Delete task (admin)
```

### Portal Endpoints

```
GET    /portal/workflows         # List available workflows
POST   /portal/workflows/:id/run # Run a workflow
GET    /portal/my-runs           # Get user's recent runs
```

### Admin Endpoints

```
GET    /admin/stats              # Workflow statistics
GET    /admin/runs               # All workflow runs with node summary
GET    /admin/schedules          # List schedules
POST   /admin/schedules          # Create schedule
PUT    /admin/schedules/:id      # Update schedule
DELETE /admin/schedules/:id      # Delete schedule
POST   /admin/schedules/:id/test # Test schedule trigger
```

## Getting Started

### Option 1: Docker (Recommended)

**Start all services:**
```bash
docker-compose up --build

# Backend: http://localhost:6000
# Frontend: http://localhost:3000
# API Docs: http://localhost:6000/docs

# Default admin login (created on first run):
# Username: admin
# Password: admin123
```

### Option 2: Local Development

**Backend:**
```bash
cd backend
pip install -r requirements.txt
python run.py
# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
# UI available at http://localhost:3000
```

## License

Private project

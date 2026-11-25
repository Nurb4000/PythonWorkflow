# System Architecture

**Version:** 1.0+  
**Last Updated:** 2026-08-25

---

## Overview

Instant Workflow is a full-stack workflow automation platform with:

- **Backend:** FastAPI (Python 3.11) + PostgreSQL
- **Frontend:** React 18 + TypeScript
- **AI:** llama.cpp (local) or OpenAI (cloud)
- **Deployment:** Docker Compose

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (React)                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │Workflow  │ │ Form     │ │ CMDB     │ │ Admin        │   │
│  │Designer  │ │ Designer │ │          │ │ Dashboard    │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼ HTTP/JSON
┌─────────────────────────────────────────────────────────────┐
│                      Backend (FastAPI)                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │Workflow  │ │ Form     │ │ CMDB     │ │ AI Service   │   │
│  │Engine    │ │ Service  │ │ Service  │ │ (llama/OpenAI)│   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │Scheduler│ │ Email    │ │ LDAP     │ │ Search       │   │
│  │          │ │ Service  │ │ Service  │ │ Service      │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼ asyncpg
┌─────────────────────────────────────────────────────────────┐
│                    PostgreSQL 15                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │workflows │ │forms     │ │cmdb      │ │users         │   │
│  │runs      │ │submissions│ │items     │ │groups        │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Backend Structure

```
backend/
├── app/
│   ├── api/                  # FastAPI route handlers
│   │   ├── workflows.py      # Workflow CRUD + execution
│   │   ├── forms.py          # Form CRUD + submissions
│   │   ├── cmdb.py           # CI types + items + relationships
│   │   ├── tasks.py          # Task management
│   │   ├── admin.py          # Admin endpoints
│   │   ├── search.py         # Unified search
│   │   ├── field_library.py  # Field library CRUD
│   │   ├── lookup.py         # Lookup API
│   │   ├── ldap.py           # LDAP integration
│   │   └── ...
│   ├── core/                 # Core configuration
│   │   ├── config.py         # Settings model
│   │   ├── database.py       # DB session management
│   │   └── security.py       # Auth utilities
│   ├── models/               # SQLAlchemy models
│   │   ├── schemas.py        # Workflow, Run, Step, Task
│   │   ├── forms.py          # Form, FormSubmission
│   │   ├── cmdb.py           # CIType, ConfigurationItem
│   │   ├── field_library.py  # FieldDefinition
│   │   └── ...
│   ├── schemas/              # Pydantic models
│   ├── services/             # Business logic
│   │   ├── workflow_engine.py
│   │   ├── form_service.py
│   │   ├── cmdb_service.py
│   │   ├── ai_service.py
│   │   ├── ldap_service.py
│   │   ├── lookup_service.py
│   │   └── ...
│   └── main.py               # FastAPI app entry point
├── alembic/                  # Database migrations
├── tests/                    # Test suite
└── requirements.txt
```

---

## Frontend Structure

```
frontend/
├── src/
│   ├── pages/                # Page components
│   │   ├── WorkflowDesigner.tsx
│   │   ├── FormDesigner.tsx
│   │   ├── CITypeManager.tsx
│   │   ├── CItemList.tsx
│   │   ├── AdminDashboard.tsx
│   │   └── ...
│   ├── components/           # Reusable components
│   │   ├── Auth.tsx
│   │   ├── DateTargetBadge.tsx
│   │   └── ...
│   ├── services/             # API client
│   │   └── api.ts
│   └── App.tsx               # Router + layout
├── package.json
└── vite.config.ts
```

---

## Data Flow

### Workflow Execution

```
User triggers workflow
    ↓
Backend creates WorkflowRun
    ↓
Engine iterates through steps
    ↓
Each step:
  - Resolves $input.* references
  - Executes via appropriate executor
  - Stores result_data
  - Updates step_instances
    ↓
Final state: completed/failed/cancelled
    ↓
Notifications sent (if configured)
```

### Form Submission

```
User fills form
    ↓
Frontend validates client-side
    ↓
POST /forms/{id}/submit
    ↓
Backend:
  - Validates against schema
  - Resolves lookup fields
  - Creates FormSubmission
  - Triggers associated workflow (if configured)
    ↓
Response: submission ID + status
```

### AI Assistance

```
User requests AI assist
    ↓
Frontend sends prompt to /ai/assist-node
    ↓
Backend:
  - Loads relevant KB context
  - Calls AI provider (llama.cpp or OpenAI)
  - Parses response
  - Validates against step schema
    ↓
Response: suggested configuration
```

---

## Database Schema

### Core Tables

| Table | Purpose |
|-------|---------|
| `workflows` | Workflow definitions |
| `workflow_steps` | Step configurations |
| `workflow_runs` | Run instances |
| `step_instances` | Per-run step executions |
| `forms` | Form definitions |
| `form_submissions` | Form data |
| `tasks` | Human task records |
| `users` | User accounts |
| `groups` | User groups |
| `ci_types` | CI type templates |
| `configuration_items` | CI instances |
| `ci_relationships` | CI links |
| `field_definitions` | Shared field library |
| `date_targets` | OLA/SLA deadlines |
| `schedules` | Workflow schedules |

### JSONB Columns

Flexible data stored as JSON:
- `workflows.config` — Workflow-level config
- `forms.schema_json` — Form field definitions
- `configuration_items.ci_data` — CI field values
- `tasks.task_data` / `result_data` — Task input/output
- `step_instances.input_data` / `output_data` — Step execution data

---

## Integration Points

### External Services

| Service | Purpose | Configuration |
|---------|---------|---------------|
| **llama.cpp** | Local AI inference | `LLAMA_CPP_URL`, `LLAMA_CPP_MODEL` |
| **OpenAI** | Cloud AI inference | `OPENAI_API_KEY`, `OPENAI_MODEL` |
| **SMTP** | Email delivery | `SMTP_HOST`, `SMTP_PORT`, etc. |
| **LDAP** | User authentication | `LDAP_SERVER_URL`, etc. |

### Internal Services

| Service | Purpose |
|---------|---------|
| **Scheduler** | Cron-like workflow execution |
| **Email Monitor** | IMAP polling for incoming email |
| **Webhook Router** | External trigger handling |

---

## Security Model

### Authentication

- **JWT tokens** (HS256) with configurable expiry
- **LDAP bind** for directory authentication
- **Session management** via localStorage

### Authorization

- **Role-based:** Admin, Developer, Staff, User
- **Group-based:** Additional permissions via group membership
- **Resource-based:** Ownership checks on create/update/delete

### Data Protection

- **Password hashing:** bcrypt with salt
- **API keys:** Stored encrypted in system_settings
- **Audit logging:** All changes tracked

---

## Performance Considerations

### Database

- **Indexes:** On frequently queried columns (name, status, created_at)
- **Pagination:** All list endpoints support page/page_size
- **Connection pooling:** asyncpg with configurable pool size

### Backend

- **Async execution:** SQLAlchemy async sessions
- **Caching:** Redis (optional) for frequently accessed data
- **Background tasks:** APScheduler for non-blocking operations

### Frontend

- **Code splitting:** Lazy loading of route components
- **Query caching:** TanStack Query with configurable stale times
- **Optimistic updates:** Immediate UI feedback on mutations

---

## Related Documentation

- [Adding Features](./adding-features.md)
- [Testing Guide](./testing.md)
- [Deployment](../deployment/production.md)

---

*Next: [Adding Features](./adding-features.md)*

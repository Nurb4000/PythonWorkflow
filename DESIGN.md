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

### Tech Stack

**Backend:**
- Python 3.11+
- FastAPI (web framework)
- SQLAlchemy (ORM)
- SQLite (dev) → PostgreSQL (production)
- APScheduler (task scheduling)

**Frontend:**
- React or Streamlit (GUI)
- React Flow (workflow designer)
- JSON Schema Form libraries (form designer)

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
- `GET /api/workflows` - List workflows
- `GET /api/workflows/{id}` - Get workflow details
- `PUT /api/workflows/{id}` - Update workflow
- `DELETE /api/workflows/{id}` - Delete workflow

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
- `POST /api/forms/{id}/submit` - Submit form data

### Admin/Reports
- `GET /api/admin/runs` - List all runs with filters
- `GET /api/admin/stats` - Workflow execution statistics
- `GET /api/admin/workflows/{id}/audit-log` - Detailed audit trail

## Migration Path: SQLite → PostgreSQL

### GUI Migration Wizard
1. **Pre-check**: Validate SQLite database integrity
2. **Backup**: Export current data
3. **Schema Transform**: Convert SQLite schema to PG syntax
   - `INTEGER PRIMARY KEY` → `SERIAL PRIMARY KEY`
   - `TEXT` → `VARCHAR` or `TEXT` (explicit)
   - Add explicit types where SQLite was loose
4. **Data Export**: Dump SQLite data to CSV/SQL
5. **PG Setup**: Create PostgreSQL database and user
6. **Import**: Load schema and data into PG
7. **Validation**: Verify row counts and data integrity
8. **Switch**: Update app config to use PG
9. **Rollback**: Option to revert if issues found

### Migration Script Features
- Progress tracking in GUI
- Error handling with detailed messages
- Test connection to PG before full migration
- Option to run in dry-run mode first

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

## Security Considerations

- Authentication: JWT or session-based
- Authorization: Role-based (admin, user, viewer)
- API keys for external integrations
- Sandboxed execution for custom code steps
- Audit logging for all actions
- Encrypted secrets for credentials

## Development Phases

### Phase 1: Core Engine
- Workflow CRUD
- Step execution framework
- Basic step types (API, DB, Email)
- SQLite storage
- Simple CLI interface

### Phase 2: Web UI
- FastAPI endpoints
- Basic React/Streamlit dashboard
- Workflow designer (visual DAG)
- Run monitoring

### Phase 3: AI Integration
- llama.cpp server setup
- Step generation API
- Prompt engineering and knowledge base
- Form schema generation

### Phase 4: Scheduling & Triggers
- Cron-based scheduling
- Manual trigger UI
- External API triggers
- Webhook support

### Phase 5: Admin Features
- Reporting dashboard
- Query tools
- User management
- Migration wizard (SQLite → PG)

### Phase 6: Form Designer
- Visual form builder
- AI-assisted form creation
- Form templates
- Submission tracking

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
│   ├── migrations/
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
│   └── migrate_sqlite_to_pg.py
└── README.md
```

## Next Steps

1. Initialize git repo
2. Set up FastAPI project structure
3. Define initial database models
4. Build core workflow engine
5. Create basic API endpoints
6. Set up llama.cpp integration
7. Design frontend wireframes
8. Implement form designer (later phase)

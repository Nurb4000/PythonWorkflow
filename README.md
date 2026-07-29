# Python Workflow System

A web-based workflow management system with AI-generated steps, scheduling, and form design capabilities.

## Features

- **Visual Workflow Designer**: Create and manage workflows with a drag-and-drop interface
- **AI-Generated Steps**: Use in-house llama.cpp server to generate workflow steps from natural language
- **Scheduling & Triggers**: Auto-trigger workflows on schedules or manually via web UI
- **Form Designer**: AI-assisted form creation for data collection
- **Admin Dashboard**: Monitoring, reporting, and query tools
- **External API**: REST API for integrations

## Tech Stack

- **Backend**: Python, FastAPI, SQLAlchemy
- **Frontend**: React/Streamlit
- **Database**: SQLite (dev) → PostgreSQL (production)
- **AI**: llama.cpp (local inference)

## Getting Started

See `DESIGN.md` for system architecture and development phases.

## Development Phases

- [x] Phase 1: Core Engine (workflow CRUD, step execution, AI integration, scheduler)
- [x] Phase 2: Web UI (React dashboard, workflow designer, admin monitoring)
- [x] Phase 3: AI Integration Enhancement (knowledge base, templates, validation, tests)
- [x] Phase 4: Scheduling & Triggers (cron jobs, webhooks, external API triggers, schedule management)
- [x] Phase 5: User Management & Access Control (authentication, RBAC, groups, portal, JWT)
- [ ] Phase 6: Form Designer (visual builder, AI-assisted form creation, submission tracking)

See `DESIGN.md` for detailed progress and next steps.

## Getting Started

### Backend
```bash
cd backend
pip install -r requirements.txt
python run.py
# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

### Frontend
```bash
cd frontend
npm install
npm run dev
# UI available at http://localhost:3000
```

## License

Private project

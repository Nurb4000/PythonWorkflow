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
- [ ] Phase 2: Web UI (dashboard, workflow designer, form designer)
- [ ] Phase 3: AI Integration Enhancement (knowledge base, validation)
- [ ] Phase 4: Scheduling & Triggers (cron, webhooks)
- [ ] Phase 5: Admin Features (reporting, user management)
- [ ] Phase 6: Form Designer (visual builder, templates)

See `DESIGN.md` for detailed progress and next steps.

## License

Private project

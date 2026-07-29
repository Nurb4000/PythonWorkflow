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

1. Core Engine (workflow CRUD, step execution)
2. Web UI (FastAPI endpoints, dashboard)
3. AI Integration (llama.cpp, step generation)
4. Scheduling & Triggers
5. Admin Features (reporting, migration wizard)
6. Form Designer

## License

Private project

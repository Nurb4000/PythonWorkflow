"""
Python Workflow System - Main Application
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import init_db, close_db, async_session_factory
from app.api import workflows, workflow_runs, admin, ai, knowledge_base, ai
from app.services.scheduler import scheduler_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Python Workflow System",
    description="Web-based workflow management with AI-generated steps",
    version="0.1.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(workflows.router, prefix="/api/workflows", tags=["workflows"])
app.include_router(workflow_runs.router, prefix="/api/workflows/{workflow_id}/runs", tags=["workflow-runs"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(ai.router, tags=["ai"])
app.include_router(knowledge_base.router, prefix="/api", tags=["knowledge-base"])


@app.on_event("startup")
async def startup_event():
    """Initialize database and scheduler on startup"""
    await init_db()
    await scheduler_service.initialize(async_session_factory)
    logger.info("Application started")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    scheduler_service.stop()
    await close_db()
    logger.info("Application stopped")


@app.get("/")
async def root():
    return {"message": "Python Workflow System API", "version": "0.1.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}

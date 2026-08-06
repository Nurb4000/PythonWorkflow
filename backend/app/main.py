"""
Python Workflow System - Main Application
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import init_db, close_db, async_session_factory
from app.api import workflows, workflow_runs, admin, ai, knowledge_base, auth, portal, forms, system_settings, tasks, webhooks, data_fields, data_query, data_export, sql_views, workflow_import_export, marketplace
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

# Include routers (nginx strips /api prefix, so backend routes exclude it)
app.include_router(workflows.router, prefix="/workflows", tags=["workflows"])
app.include_router(workflow_runs.router, prefix="/workflows/{workflow_id}/runs", tags=["workflow-runs"])
app.include_router(workflow_runs.runs_router, tags=["workflow-runs"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(ai.router, tags=["ai"])
app.include_router(knowledge_base.router, tags=["knowledge-base"])
app.include_router(auth.router)
app.include_router(portal.router)
app.include_router(forms.router, tags=["forms"])
app.include_router(system_settings.router, tags=["system-settings"])
app.include_router(tasks.router, tags=["tasks"])
app.include_router(webhooks.router, tags=["webhooks"])
app.include_router(data_fields.router, prefix="/data-fields", tags=["data-fields"])
app.include_router(data_query.router, prefix="/data-query", tags=["data-query"])
app.include_router(data_export.router, prefix="/data-export", tags=["data-export"])
app.include_router(sql_views.router, prefix="/sql-views", tags=["sql-views"])
app.include_router(workflow_import_export.router, prefix="/workflows", tags=["workflow-import-export"])
app.include_router(marketplace.router, prefix="/marketplace", tags=["marketplace"])


async def create_default_admin():
    """Create default admin user if none exists"""
    try:
        async with async_session_factory() as db:
            from sqlalchemy import select
            from app.models.auth import User
            
            stmt = select(User)
            result = await db.execute(stmt)
            users = result.scalars().all()
            
            if not users:
                # No users exist, create default admin
                from passlib.context import CryptContext
                pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
                
                admin = User(
                    username="admin",
                    email="admin@example.com",
                    password_hash=pwd_context.hash("admin123"),
                    full_name="Administrator",
                    role="admin",
                    is_active=True,
                    is_verified=True
                )
                db.add(admin)
                await db.commit()
                logger.info("Created default admin user (username: admin, password: admin123)")
            else:
                logger.info(f"Found {len(users)} existing user(s), skipping admin creation")
    except Exception as e:
        logger.error(f"Failed to create default admin: {str(e)}")


@app.on_event("startup")
async def startup_event():
    """Initialize database and scheduler on startup"""
    await init_db()
    await create_default_admin()
    await scheduler_service.initialize(async_session_factory)
    from app.services.sql_view_service import sql_view_service
    async with async_session_factory() as db:
        await sql_view_service.sync_views(db)
    await scheduler_service.start_email_monitor()
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

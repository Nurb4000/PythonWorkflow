"""
Python Workflow System - Main Application
"""
import asyncio
import json
import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.database import init_db, close_db, async_session_factory
from app.api import workflows, workflow_runs, admin, ai, knowledge_base, auth, portal, forms, system_settings, tasks, webhooks, data_fields, data_query, data_export, sql_views, workflow_import_export, marketplace, cmdb, services
from app.services.scheduler import scheduler_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEMO_METADATA = {
    "hello-world.xml": {
        "name": "Hello World",
        "description": "A simple linear workflow that fetches a random cat fact via API and sends an email notification. Great for testing import/export.",
        "category": "General",
        "tags": ["demo", "api", "email", "getting-started"],
    },
    "expense-approval.xml": {
        "name": "Expense Approval",
        "description": "A complete expense approval process with form submission, manager approval, branching logic, and database updates.",
        "category": "Approvals & Tasks",
        "tags": ["demo", "approval", "form", "branching"],
    },
    "data-report.xml": {
        "name": "Data Report",
        "description": "SQL query to report node to scheduled email delivery. Demonstrates data pipeline patterns.",
        "category": "Reporting",
        "tags": ["demo", "report", "sql", "scheduled"],
    },
    "form-collection.xml": {
        "name": "Form Collection",
        "description": "Form submission followed by human review and conditional database update. Shows form-to-task workflows.",
        "category": "Onboarding",
        "tags": ["demo", "form", "human-task", "conditional"],
    },
    "scheduled-cleanup.xml": {
        "name": "Scheduled Cleanup",
        "description": "Weekly cron trigger that queries old data, generates a report, and emails a summary. Maintenance workflow pattern.",
        "category": "Schedules & Maintenance",
        "tags": ["demo", "scheduled", "cleanup", "maintenance"],
    },
    "4-column-demo.xml": {
        "name": "4 Column Demo",
        "description": "Demonstrates a 4-column entry form with Info Text labels. Submitter fills the intake form in the portal; data passes through and pre-fills the staff review task.",
        "category": "Forms & Tasks",
        "tags": ["demo", "form", "4-column", "review", "pass-through"],
    },
}

_demo_seeded = False

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
app.include_router(cmdb.router, prefix="/cmdb", tags=["cmdb"])
app.include_router(services.router, prefix="/services", tags=["services"])


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


async def seed_marketplace_demos():
    """Seed demo marketplace items on startup (idempotent)"""
    global _demo_seeded
    if _demo_seeded:
        return
    try:
        from app.models.auth import User
        from app.models.marketplace import MarketplaceItem

        demo_dir = Path(__file__).resolve().parent / "data" / "demo-workflows"
        if not demo_dir.is_dir():
            logger.warning(f"Demo directory not found: {demo_dir}")
            _demo_seeded = True
            return

        async with async_session_factory() as db:
            result = await db.execute(select(User).where(User.role == "admin").limit(1))
            admin_user = result.scalar_one_or_none()
            if not admin_user:
                logger.warning("No admin user found, skipping marketplace demo seeding")
                _demo_seeded = True
                return

            seeded = 0
            skipped = 0
            for filename, metadata in DEMO_METADATA.items():
                fpath = demo_dir / filename
                if not fpath.is_file():
                    logger.warning(f"Demo file not found: {fpath}")
                    continue

                result = await db.execute(
                    select(MarketplaceItem).where(
                        MarketplaceItem.name == metadata["name"],
                        MarketplaceItem.author_id == admin_user.id,
                    )
                )
                if result.scalar_one_or_none():
                    skipped += 1
                    continue

                content = fpath.read_text(encoding="utf-8")
                item = MarketplaceItem(
                    item_type="workflow",
                    name=metadata["name"],
                    description=metadata["description"],
                    category=metadata["category"],
                    author_id=admin_user.id,
                    content=content,
                    content_format="xml",
                    status="published",
                    is_active=True,
                    downloads_count=0,
                )
                item.tags_list = metadata["tags"]
                db.add(item)
                await db.flush()
                seeded += 1
                logger.info(f"Seeded demo: {item.name} (id={item.id})")

            await db.commit()
            logger.info(f"Marketplace demo seeding done. Seeded={seeded}, Skipped={skipped}")

        _demo_seeded = True
    except Exception as e:
        logger.error(f"Marketplace demo seeding failed: {e}", exc_info=True)


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
    asyncio.create_task(seed_marketplace_demos())
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

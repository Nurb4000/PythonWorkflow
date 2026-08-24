"""
Instant Workflow - Main Application
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
from app.api import workflows, workflow_runs, admin, ai, knowledge_base, auth, portal, forms, system_settings, tasks, webhooks, data_fields, data_query, data_export, sql_views, workflow_import_export, marketplace, cmdb, services, date_targets
from app.services.scheduler import scheduler_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEMO_METADATA = {
    "hello-world.xml": {
        "name": "Hello World",
        "description": "A simple linear workflow that fetches a random cat fact via API, displays it in a report, and sends an email notification. Great for testing import/export.",
        "category": "General",
        "tags": ["demo", "api", "report", "email", "getting-started"],
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
    "incident-management.xml": {
        "name": "Incident Management",
        "description": "Multi-team incident handling with triage routing, SLA tracking, and optional QC verification. Demonstrates break-fix workflow patterns.",
        "category": "IT Operations",
        "tags": ["demo", "incident", "triage", "sla", "multi-team", "itil"],
    },
    "change-management.xml": {
        "name": "Change Management",
        "description": "Multi-stage change approval workflow with manager sign-off, team supervisor review, CAB assessment, date-targeted implementation, and post-implementation review.",
        "category": "IT Operations",
        "tags": ["demo", "change", "approval", "cab", "date-target", "itil"],
    },
}

_demo_seeded = False

app = FastAPI(
    title="Instant Workflow",
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
app.include_router(date_targets.router, prefix="/date-targets", tags=["date-targets"])


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

                content = fpath.read_text(encoding="utf-8")

                # Check for existing item — update content so XML changes propagate
                result = await db.execute(
                    select(MarketplaceItem).where(
                        MarketplaceItem.name == metadata["name"],
                        MarketplaceItem.author_id == admin_user.id,
                    )
                )
                existing = result.scalar_one_or_none()
                if existing:
                    old_steps = existing.content.count("<Step")
                    existing.content = content
                    existing.description = metadata["description"]
                    existing.category = metadata["category"]
                    existing.version += 1
                    existing.tags_list = metadata["tags"]
                    new_steps = content.count("<Step")
                    logger.info(f"Updated demo: {metadata['name']} (id={existing.id}, version={existing.version}, steps: {old_steps}->{new_steps})")
                    skipped += 1
                    continue
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

            # Seed KB article demos
            kb_demos = [
                {
                    "name": "Getting Started Guide",
                    "description": "A comprehensive guide for new users on how to navigate the system, submit requests, and track their workflow progress.",
                    "category": "General",
                    "tags": ["demo", "getting-started", "guide"],
                    "content": {
                        "title": "Getting Started Guide",
                        "slug": "getting-started-guide",
                        "content": """# Getting Started Guide

Welcome to the workflow system! This guide will help you get up and running quickly.

## Navigating the System

- **Offerings**: Browse available workflows and services
- **My Submissions**: Track your submitted requests
- **Catalog**: Explore all available services

## Submitting a Request

1. Go to the Offerings page
2. Select a workflow you'd like to use
3. Fill out the required form
4. Submit and track progress in My Submissions

## Need Help?

Check the Knowledge Base for detailed articles or contact your administrator.""",
                        "is_published": True,
                        "sort_order": 1,
                    },
                },
                {
                    "name": "FAQ — Common Questions",
                    "description": "Frequently asked questions about account management, workflow status, and system features.",
                    "category": "General",
                    "tags": ["demo", "faq", "help"],
                    "content": {
                        "title": "FAQ — Common Questions",
                        "slug": "faq-common-questions",
                        "content": """# Frequently Asked Questions

## Account & Access

**Q: How do I reset my password?**
A: Click the 'Change Password' button in the top navigation bar.

**Q: I can't see a workflow I was told about.**
A: Workflows may be restricted to specific groups. Contact your administrator to verify your group membership.

## Workflow Status

**Q: What does 'Pending' mean?**
A: Your request has been submitted and is waiting for the next step in the workflow.

**Q: How long do approvals take?**
A: This depends on the workflow configuration and the availability of approvers. Check with your team lead for expected timelines.

## General

**Q: Can I edit a submission after sending it?**
A: No, submissions cannot be edited once submitted. If you need changes, please submit a new request.""",
                        "is_published": True,
                        "sort_order": 2,
                    },
                },
            ]

            kb_seeded = 0
            kb_skipped = 0
            for demo in kb_demos:
                result = await db.execute(
                    select(MarketplaceItem).where(
                        MarketplaceItem.name == demo["name"],
                        MarketplaceItem.author_id == admin_user.id,
                    )
                )
                existing = result.scalar_one_or_none()
                if existing:
                    existing.content = json.dumps(demo["content"])
                    existing.description = demo["description"]
                    existing.category = demo["category"]
                    existing.version += 1
                    existing.tags_list = demo["tags"]
                    logger.info(f"Updated KB demo: {demo['name']} (id={existing.id}, version={existing.version})")
                    kb_skipped += 1
                    continue

                item = MarketplaceItem(
                    item_type="kb_article",
                    name=demo["name"],
                    description=demo["description"],
                    category=demo["category"],
                    author_id=admin_user.id,
                    content=json.dumps(demo["content"]),
                    content_format="json",
                    status="published",
                    is_active=True,
                    downloads_count=0,
                )
                item.tags_list = demo["tags"]
                db.add(item)
                await db.flush()
                kb_seeded += 1
                logger.info(f"Seeded KB demo: {item.name} (id={item.id})")

            await db.commit()
            logger.info(f"Marketplace demo seeding done. Workflows: Seeded={seeded}, Skipped={skipped}. KB Articles: Seeded={kb_seeded}, Skipped={kb_skipped}")

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
    return {"message": "Instant Workflow API", "version": "0.1.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}

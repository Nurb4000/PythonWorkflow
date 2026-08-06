#!/usr/bin/env python3
"""
Seed script: migrate demo-workflows/*.xml into marketplace_items.

Idempotent — runs safely multiple times. Skips items that already exist
(matched by name). Creates a "Demo" user if one doesn't exist.

Usage (inside backend venv):
    python scripts/seed_marketplace_demos.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

# Allow importing from backend/ directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, insert
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.marketplace import MarketplaceItem
from app.models.auth import User


# ── Demo metadata catalog ────────────────────────────────────────────────
DEMO_METADATA = {
    "hello-world.xml": {
        "name": "Hello World",
        "description": "A simple linear workflow that makes an API call and sends an email notification. Great for testing import/export.",
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
}


def parse_demo_metadata(xml_content: str) -> dict:
    """Extract name and description from XML Metadata section (fallback)."""
    try:
        root = ET.fromstring(xml_content)
        meta = root.find("Metadata")
        if meta is not None:
            name_el = meta.find("Name")
            desc_el = meta.find("Description")
            return {
                "name": name_el.text if name_el is not None else "",
                "description": desc_el.text if desc_el is not None else "",
            }
    except ET.ParseError:
        pass
    return {}


async def seed():
    database_url = os.environ.get(
        "DATABASE_URL",
        "sqlite+aiosqlite:///./test.db"
    )

    engine = create_async_engine(database_url, echo=False)

    # Create all tables if they don't exist (idempotent)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    demo_dir = Path(__file__).resolve().parent.parent / "backend" / "app" / "data" / "demo-workflows"
    if not demo_dir.is_dir():
        print(f"[seed] Demo directory not found: {demo_dir}")
        return

    async with async_session() as db:
        # Ensure a "Demo" author user exists
        result = await db.execute(select(User).where(User.username == "demo"))
        demo_user = result.scalar_one_or_none()

        if not demo_user:
            demo_user = User(
                username="demo",
                email="demo@pythonworkflow.local",
                full_name="Demo System",
                role="admin",
                is_active=True,
                password_hash="",  # Not login-able — system user
            )
            db.add(demo_user)
            await db.flush()
            print(f"[seed] Created demo user (id={demo_user.id})")
        else:
            print(f"[seed] Using existing demo user (id={demo_user.id})")

        seeded = 0
        skipped = 0

        for filename, metadata in DEMO_METADATA.items():
            fpath = demo_dir / filename
            if not fpath.is_file():
                print(f"[seed] File not found: {fpath}, skipping")
                continue

            # Check if already seeded (by name)
            result = await db.execute(
                select(MarketplaceItem).where(
                    MarketplaceItem.name == metadata["name"],
                    MarketplaceItem.author_id == demo_user.id,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                print(f"[seed] Already seeded: {metadata['name']} (id={existing.id}), skipping")
                skipped += 1
                continue

            content = fpath.read_text(encoding="utf-8")
            fallback = parse_demo_metadata(content)

            item = MarketplaceItem(
                item_type="workflow",
                name=metadata["name"],
                description=metadata["description"] or fallback.get("description", ""),
                category=metadata["category"],
                author_id=demo_user.id,
                content=content,
                content_format="xml",
                status="published",
                is_active=True,
                downloads_count=0,
            )
            item.tags_list = metadata["tags"]

            db.add(item)
            await db.flush()
            await db.refresh(item)
            seeded += 1
            print(f"[seed] Seeded: {item.name} (id={item.id})")

        await db.commit()

    print(f"\n[seed] Done. Seeded={seeded}, Skipped={skipped}")


if __name__ == "__main__":
    asyncio.run(seed())

"""Tests for the demo workflow seed (fresh-DB path + idempotency)."""
import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.auth import User
from app.models.forms import Form
from app.models.schemas import Workflow, WorkflowStep
from app.services.demo_seed import (
    seed_demo_workflow,
    DEMO_WORKFLOW_NAME,
    ENTRY_FORM_NAME,
    STAFF_FORM_NAME,
)


@pytest.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fk(dbapi_conn, record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def seeded_db(db_session):
    admin = User(username="demo", email="demo@test.local", role="admin", is_active=True, password_hash="")
    staff = User(username="staff", email="staff@test.local", role="staff", is_active=True, password_hash="")
    db_session.add_all([admin, staff])
    await db_session.commit()
    return db_session


@pytest.mark.asyncio
async def test_seed_creates_demo_workflow(seeded_db):
    assert await seed_demo_workflow(seeded_db) is True

    result = await seeded_db.execute(
        select(Workflow).where(Workflow.name == DEMO_WORKFLOW_NAME)
    )
    wf = result.scalar_one()
    assert wf.environment == "production"
    assert wf.is_published is True
    assert wf.is_active is True
    assert wf.portal_visible is True
    assert wf.entry_form_id is not None

    steps = (await seeded_db.execute(
        select(WorkflowStep).where(WorkflowStep.workflow_id == wf.id)
    )).scalars().all()
    assert len(steps) == 1
    assert steps[0].step_type == "human_task"
    assert steps[0].definition["form_id"] is not None
    assert steps[0].definition["assigned_to_user_id"] is not None

    entry_form = (await seeded_db.execute(
        select(Form).where(Form.name == ENTRY_FORM_NAME)
    )).scalar_one()
    assert entry_form.schema_json["columns"] == 4
    assert entry_form.is_published is True
    assert entry_form.schema_json["properties"]["intro"]["type"] == "info"

    staff_form = (await seeded_db.execute(
        select(Form).where(Form.name == STAFF_FORM_NAME)
    )).scalar_one()
    assert staff_form.schema_json["columns"] == 2


@pytest.mark.asyncio
async def test_seed_is_idempotent(seeded_db):
    assert await seed_demo_workflow(seeded_db) is True
    assert await seed_demo_workflow(seeded_db) is False

    result = await seeded_db.execute(select(Workflow).where(Workflow.name == DEMO_WORKFLOW_NAME))
    assert len(result.scalars().all()) == 1
    result = await seeded_db.execute(select(Form).where(Form.name == ENTRY_FORM_NAME))
    assert len(result.scalars().all()) == 1

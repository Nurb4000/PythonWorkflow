"""Reproduction test for entry_form_id persistence across updates."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.core.database import Base
from app.services.workflow_engine import WorkflowEngine
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate


@pytest.fixture
async def db_session(db_engine):
    async_session = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


@pytest.mark.asyncio
async def test_entry_form_persistence(db_session):
    engine = WorkflowEngine()
    wf = await engine.create_workflow(db_session, WorkflowCreate(name="WF"))
    assert wf.entry_form_id is None

    # 1. Set entry form
    updated = await engine.update_workflow(db_session, wf.id, WorkflowUpdate(entry_form_id=42))
    assert updated.entry_form_id == 42

    # 2. Update something else — entry_form_id must NOT be cleared
    updated2 = await engine.update_workflow(db_session, wf.id, WorkflowUpdate(name="Renamed"))
    assert updated2.entry_form_id == 42

    # 3. Reload from DB fresh
    from app.models.schemas import Workflow
    async with db_session.bind.connect() as conn:
        pass
    result = await db_session.execute(select(Workflow).where(Workflow.id == wf.id))
    fresh = result.scalar_one()
    assert fresh.entry_form_id == 42

    # 4. Explicitly clear it
    updated3 = await engine.update_workflow(db_session, wf.id, WorkflowUpdate(entry_form_id=None))
    assert updated3.entry_form_id is None


@pytest.mark.asyncio
async def test_entry_form_set_on_create_persists(db_session):
    engine = WorkflowEngine()
    wf = await engine.create_workflow(
        db_session, WorkflowCreate(name="WF", entry_form_id=7)
    )
    assert wf.entry_form_id == 7

    from app.models.schemas import Workflow
    result = await db_session.execute(select(Workflow).where(Workflow.id == wf.id))
    fresh = result.scalar_one()
    assert fresh.entry_form_id == 7

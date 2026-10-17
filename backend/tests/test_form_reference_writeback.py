"""
Regression tests for the M5 reference-field writeback in form_service.submit_form.

Verifies that a reference field writes its value back to a *real* column on the
target table, and that a `ref_column` which does not exist on the model is
skipped gracefully (logged + no write) instead of raising AttributeError or
writing to the wrong column.
"""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.auth import User
from app.models.forms import Form
from app.models.schemas import Task
from app.services.form_service import form_service


@pytest.fixture
async def db_session(db_engine):
    async_session = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


async def _make_form(db, ref_column: str):
    form = Form(
        name="Reference Form",
        is_active=True,
        is_published=True,
        schema_json={
            "type": "object",
            "title": "Reference Form",
            "properties": {
                "incident_desc": {
                    "type": "string",
                    "source": "reference",
                    "ref_table": "tasks",
                    "ref_column": ref_column,
                }
            },
            "required": [],
        },
    )
    db.add(form)
    await db.flush()
    return form


async def _make_task(db, title: str) -> Task:
    task = Task(title=title)
    db.add(task)
    await db.flush()
    return task


async def _make_user(db) -> int:
    user = User(username="ref_tester", email="ref_tester@test.local",
                password_hash="x", role="user")
    db.add(user)
    await db.flush()
    return user.id


async def _get_task(db, task_id: int) -> Task:
    result = await db.execute(select(Task).where(Task.id == task_id))
    return result.scalar_one_or_none()


@pytest.mark.asyncio
async def test_valid_ref_column_writes_back(db_session):
    task = await _make_task(db_session, "Original title")
    form = await _make_form(db_session, ref_column="title")
    user_id = await _make_user(db_session)

    data = {"incident_desc": "Updated title", f"__ref_incident_desc": task.id}
    await form_service.submit_form(db_session, form.id, data, user_id=user_id)

    refreshed = await _get_task(db_session, task.id)
    assert refreshed.title == "Updated title"


@pytest.mark.asyncio
async def test_unknown_ref_column_is_skipped_not_crashed(db_session):
    task = await _make_task(db_session, "Original title")
    form = await _make_form(db_session, ref_column="not_a_real_column")
    user_id = await _make_user(db_session)

    data = {"incident_desc": "Hacked value", f"__ref_incident_desc": task.id}
    # Must not raise AttributeError for the bad column.
    await form_service.submit_form(db_session, form.id, data, user_id=user_id)

    refreshed = await _get_task(db_session, task.id)
    assert refreshed.title == "Original title"  # writeback skipped


@pytest.mark.asyncio
async def test_valid_ref_column_still_creates_submission(db_session):
    """Even when the column is invalid, the submission itself is recorded."""
    task = await _make_task(db_session, "Original title")
    form = await _make_form(db_session, ref_column="bogus")
    user_id = await _make_user(db_session)

    data = {"incident_desc": "x", f"__ref_incident_desc": task.id}
    submission = await form_service.submit_form(db_session, form.id, data, user_id=user_id)

    assert submission.id is not None
    assert submission.status == "submitted"

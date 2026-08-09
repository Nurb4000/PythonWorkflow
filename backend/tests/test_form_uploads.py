"""Tests for form file upload audit records and download access control."""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.auth import User
from app.models.forms import FormUpload
from app.models.schemas import Task, Workflow, WorkflowRun
from app.api.forms import _contains_ref, _file_accessible


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


async def make_user(db, username: str, role: str = "user"):
    user = User(
        username=username,
        email=f"{username}@test.local",
        password_hash="x",
        role=role,
    )
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_contains_ref_recurses_nested_data(db_session):
    file_ref = "abc123_report.pdf"
    data = {
        "upload": file_ref,
        "nested": {"deep": [{"deeper": file_ref}]},
        "other": "something else",
    }
    assert _contains_ref(data, file_ref) is True
    assert _contains_ref(data, "missing.pdf") is False
    assert _contains_ref([{"a": file_ref}], file_ref) is True


@pytest.mark.asyncio
async def test_upload_recorded_with_uploader(db_session):
    db = db_session
    uploader = await make_user(db, "alice", role="user")
    upload = FormUpload(
        original_name="report.pdf",
        stored_name=f"{'a' * 32}_report.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        uploaded_by=uploader.id,
    )
    db.add(upload)
    await db.commit()

    rows = (await db.execute(select(FormUpload))).scalars().all()
    assert len(rows) == 1
    assert rows[0].original_name == "report.pdf"
    assert rows[0].uploaded_by == uploader.id
    assert rows[0].stored_name.endswith("_report.pdf")


@pytest.mark.asyncio
async def test_download_access_uploader_and_admin(db_session):
    db = db_session
    uploader = await make_user(db, "alice", role="user")
    other = await make_user(db, "bob", role="user")
    admin = await make_user(db, "root", role="admin")
    stored = f"{'b' * 32}_report.pdf"
    db.add(FormUpload(
        original_name="report.pdf",
        stored_name=stored,
        content_type="application/pdf",
        size_bytes=10,
        uploaded_by=uploader.id,
    ))
    await db.commit()

    assert await _file_accessible(db, uploader, stored) is True
    assert await _file_accessible(db, admin, stored) is True
    assert await _file_accessible(db, other, stored) is False


@pytest.mark.asyncio
async def test_download_access_staff_with_assigned_task(db_session):
    db = db_session
    staff = await make_user(db, "carol", role="staff")
    other_staff = await make_user(db, "dave", role="staff")
    stored = f"{'c' * 32}_report.pdf"

    wf = Workflow(name="WF")
    db.add(wf)
    await db.flush()
    run = WorkflowRun(workflow_id=wf.id, status="waiting", input_data={"attachments": [stored]})
    db.add(run)
    await db.flush()
    task = Task(
        workflow_run_id=run.id,
        title="Review",
        status="open",
        assigned_to_user_id=staff.id,
        task_data={},
    )
    db.add(task)
    db.add(FormUpload(
        original_name="report.pdf",
        stored_name=stored,
        content_type="application/pdf",
        size_bytes=10,
        uploaded_by=staff.id,
    ))
    await db.commit()

    # Staff with a task on the run that references the file can download it.
    assert await _file_accessible(db, staff, stored) is True
    # Another staff member with no task referencing the file cannot.
    assert await _file_accessible(db, other_staff, stored) is False


@pytest.mark.asyncio
async def test_unknown_file_not_accessible_to_user(db_session):
    db = db_session
    user = await make_user(db, "eve", role="user")
    assert await _file_accessible(db, user, "not_in_table.pdf") is False

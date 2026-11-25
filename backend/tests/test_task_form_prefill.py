"""Tests for pre-filling human task forms with data from earlier in the run."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.forms import Form
from app.models.schemas import Workflow, WorkflowStep, WorkflowRun, StepInstance
from app.services.workflow_engine import WorkflowEngine


@pytest.fixture
async def db_session(db_engine):
    async_session = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


async def make_form(db, schema_properties: dict):
    form = Form(
        name="Staff Form",
        schema_json={
            "type": "object",
            "title": "Staff Form",
            "properties": schema_properties,
            "required": [],
        },
    )
    db.add(form)
    await db.flush()
    return form


async def make_human_run(db, form_id: int, input_data: dict, task_data: dict = None):
    wf = Workflow(name="WF")
    db.add(wf)
    await db.flush()
    step = WorkflowStep(
        workflow_id=wf.id,
        step_type="human_task",
        position=1,
        title="Approval",
        definition={
            "form_id": form_id,
            "task_data": task_data or {},
        },
    )
    db.add(step)
    run = WorkflowRun(workflow_id=wf.id, status="running", input_data=input_data)
    db.add(run)
    await db.flush()
    instance = StepInstance(
        workflow_run_id=run.id,
        step_id=step.id,
        status="pending",
        input_data=input_data.copy(),
        position=1,
    )
    db.add(instance)
    return wf, step, run, instance


@pytest.mark.asyncio
async def test_human_task_form_prefilled_from_run_data(db_session):
    db = db_session
    form = await make_form(db, {
        "notes": {"type": "string", "title": "Notes"},
        "approved": {"type": "boolean", "title": "Approved"},
        "amount": {"type": "number", "title": "Amount"},
    })
    wf, step, run, instance = await make_human_run(
        db,
        form.id,
        {
            "notes": "Customer request",
            "approved": True,
            "amount": 42.5,
            # metadata/cruft that is NOT a form field must not leak in
            "task_id": 99,
            "internal_meta": {"x": 1},
        },
    )
    await db.commit()

    engine = WorkflowEngine()
    continued = await engine._handle_human_step(db, run, instance, step)
    assert continued is False

    from app.models.schemas import Task
    from sqlalchemy import select
    result = await db.execute(select(Task).where(Task.workflow_run_id == run.id))
    task = result.scalar_one()
    assert task.form_id == form.id
    assert task.task_data == {
        "notes": "Customer request",
        "approved": True,
        "amount": 42.5,
    }


@pytest.mark.asyncio
async def test_explicit_task_data_wins_over_prefill(db_session):
    db = db_session
    form = await make_form(db, {
        "notes": {"type": "string", "title": "Notes"},
        "amount": {"type": "number", "title": "Amount"},
    })
    wf, step, run, instance = await make_human_run(
        db,
        form.id,
        {"notes": "Customer request", "amount": 42.5, "noise": "ignored"},
        task_data={"notes": "Explicit override"},
    )
    await db.commit()

    engine = WorkflowEngine()
    await engine._handle_human_step(db, run, instance, step)

    from app.models.schemas import Task
    from sqlalchemy import select
    result = await db.execute(select(Task).where(Task.workflow_run_id == run.id))
    task = result.scalar_one()
    assert task.task_data == {
        "notes": "Explicit override",
        "amount": 42.5,
    }


@pytest.mark.asyncio
async def test_no_form_means_no_prefill(db_session):
    db = db_session
    wf = Workflow(name="WF")
    db.add(wf)
    await db.flush()
    step = WorkflowStep(
        workflow_id=wf.id,
        step_type="human_task",
        position=1,
        title="No Form",
        definition={},
    )
    db.add(step)
    run = WorkflowRun(workflow_id=wf.id, status="running", input_data={"notes": "x"})
    db.add(run)
    await db.flush()
    instance = StepInstance(
        workflow_run_id=run.id,
        step_id=step.id,
        status="pending",
        input_data={"notes": "x"},
        position=1,
    )
    db.add(instance)
    await db.commit()

    engine = WorkflowEngine()
    await engine._handle_human_step(db, run, instance, step)

    from app.models.schemas import Task
    from sqlalchemy import select
    result = await db.execute(select(Task).where(Task.workflow_run_id == run.id))
    task = result.scalar_one()
    assert task.task_data == {}

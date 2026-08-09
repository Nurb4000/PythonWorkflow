"""
Demo workflow seeding.

Creates the "Demo: 4-Column Intake with Review" workflow on startup so the
4-column entry form (with Info Text labels) and the staff pass-through review
task are available on a fresh rebuild. Idempotent: skips everything if the
workflow already exists.
"""
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import User
from app.models.forms import Form
from app.models.schemas import Workflow, WorkflowStep

logger = logging.getLogger(__name__)

DEMO_WORKFLOW_NAME = "Demo: 4-Column Intake with Review"

ENTRY_FORM_NAME = "Demo: 4-Column Intake"
STAFF_FORM_NAME = "Demo: Staff Review"

ENTRY_FORM_SCHEMA = {
    "type": "object",
    "columns": 4,
    "properties": {
        "intro": {
            "name": "intro", "type": "info", "title": "Demo: 4-Column Intake Form",
            "content": "This entry form uses a 4-column grid. Info Text elements like this one span the full width of the form.",
            "text_align": "center", "required": False, "source": "form",
        },
        "first_name": {
            "name": "first_name", "type": "string", "title": "First Name",
            "required": True, "column": 0, "data_size": "medium", "source": "form",
        },
        "last_name": {
            "name": "last_name", "type": "string", "title": "Last Name",
            "required": True, "column": 1, "data_size": "medium", "source": "form",
        },
        "email": {
            "name": "email", "type": "email", "title": "Email",
            "required": True, "column": 2, "data_size": "medium", "source": "form",
        },
        "phone": {
            "name": "phone", "type": "string", "title": "Phone",
            "required": False, "column": 3, "data_size": "medium", "source": "form",
        },
        "section2": {
            "name": "section2", "type": "info", "title": "Request Details",
            "content": "The next row also uses all four columns: a dropdown, a dropdown, a dropdown, and a number.",
            "text_align": "left", "required": False, "source": "form",
        },
        "department": {
            "name": "department", "type": "select", "title": "Department",
            "required": True, "column": 0,
            "options": ["Finance", "HR", "IT", "Operations", "Sales"], "source": "form",
        },
        "request_type": {
            "name": "request_type", "type": "select", "title": "Request Type",
            "required": True, "column": 1,
            "options": ["New Request", "Change Request", "Incident", "Approval"], "source": "form",
        },
        "priority": {
            "name": "priority", "type": "select", "title": "Priority",
            "required": True, "column": 2,
            "options": ["Low", "Medium", "High", "Urgent"], "source": "form",
        },
        "amount": {
            "name": "amount", "type": "number", "title": "Amount",
            "required": False, "column": 3, "source": "form",
        },
        "notes": {
            "name": "notes", "type": "textarea", "title": "Details / Notes",
            "required": False, "column": 0, "data_size": "long", "source": "form",
        },
    },
    "required": ["first_name", "last_name", "email", "department", "request_type", "priority"],
}

STAFF_FORM_SCHEMA = {
    "type": "object",
    "columns": 2,
    "properties": {
        "review_heading": {
            "name": "review_heading", "type": "info", "title": "Staff Review",
            "content": "These fields were pre-filled automatically from the submitter's entry form (data pass-through).",
            "text_align": "left", "required": False, "source": "form",
        },
        "first_name": {
            "name": "first_name", "type": "string", "title": "First Name",
            "required": False, "column": 0, "data_size": "medium", "source": "form",
        },
        "last_name": {
            "name": "last_name", "type": "string", "title": "Last Name",
            "required": False, "column": 1, "data_size": "medium", "source": "form",
        },
        "email": {
            "name": "email", "type": "email", "title": "Email",
            "required": False, "column": 0, "data_size": "medium", "source": "form",
        },
        "phone": {
            "name": "phone", "type": "string", "title": "Phone",
            "required": False, "column": 1, "data_size": "medium", "source": "form",
        },
        "department": {
            "name": "department", "type": "string", "title": "Department",
            "required": False, "column": 0, "data_size": "medium", "source": "form",
        },
        "request_type": {
            "name": "request_type", "type": "string", "title": "Request Type",
            "required": False, "column": 1, "data_size": "medium", "source": "form",
        },
        "priority": {
            "name": "priority", "type": "string", "title": "Priority",
            "required": False, "column": 0, "data_size": "medium", "source": "form",
        },
        "amount": {
            "name": "amount", "type": "number", "title": "Amount",
            "required": False, "column": 1, "source": "form",
        },
        "notes": {
            "name": "notes", "type": "textarea", "title": "Details / Notes (from entry form)",
            "required": False, "column": 0, "data_size": "long", "source": "form",
        },
        "review_notes": {
            "name": "review_notes", "type": "textarea", "title": "Staff Review Notes",
            "required": False, "column": 1, "data_size": "long", "source": "form",
        },
    },
    "required": [],
}


async def _resolve_author_user(db: AsyncSession) -> User | None:
    """Prefer the demo user, else the first admin/developer."""
    result = await db.execute(select(User).where(User.username == "demo"))
    user = result.scalar_one_or_none()
    if user:
        return user
    result = await db.execute(
        select(User).where(User.role.in_(["admin", "developer"])).limit(1)
    )
    return result.scalar_one_or_none()


async def _resolve_staff_user(db: AsyncSession) -> User | None:
    """Prefer the 'staff' username, else the first staff-role user."""
    result = await db.execute(select(User).where(User.username == "staff"))
    user = result.scalar_one_or_none()
    if user:
        return user
    result = await db.execute(select(User).where(User.role == "staff").limit(1))
    return result.scalar_one_or_none()


async def _find_or_create_form(db: AsyncSession, name: str, description: str,
                               schema: dict, author_id: int) -> Form:
    result = await db.execute(select(Form).where(Form.name == name))
    form = result.scalar_one_or_none()
    if form:
        return form
    form = Form(
        name=name,
        description=description,
        schema_json=schema,
        version=1,
        is_published=True,
        created_by=author_id,
        environment="test",
    )
    db.add(form)
    await db.flush()
    return form


async def seed_demo_workflow(db: AsyncSession) -> bool:
    """Create the demo workflow + forms if missing. Returns True if seeded."""
    result = await db.execute(select(Workflow).where(Workflow.name == DEMO_WORKFLOW_NAME))
    if result.scalar_one_or_none():
        logger.info("Demo workflow already exists, skipping")
        return False

    author = await _resolve_author_user(db)
    staff = await _resolve_staff_user(db)
    author_id = author.id if author else None

    entry_form = await _find_or_create_form(
        db, ENTRY_FORM_NAME, "4-column layout with Info Text labels",
        ENTRY_FORM_SCHEMA, author_id,
    )
    staff_form = await _find_or_create_form(
        db, STAFF_FORM_NAME, "2-column review form prefilled from the entry form",
        STAFF_FORM_SCHEMA, author_id,
    )

    workflow = Workflow(
        name=DEMO_WORKFLOW_NAME,
        description="Submitter fills the 4-column entry form (with Info Text labels) "
                    "in the portal; the data passes through and pre-fills the staff review task.",
        version=1,
        is_active=True,
        is_published=True,
        environment="production",
        portal_icon="clipboard-list",
        portal_order=1,
        portal_visible=True,
        entry_form_id=entry_form.id,
        created_by=author_id,
    )
    db.add(workflow)
    await db.flush()

    step = WorkflowStep(
        workflow_id=workflow.id,
        step_type="human_task",
        position=0,
        title="Review Intake",
        description="Review the submitter's intake form.",
        definition={
            "form_id": staff_form.id,
            "assigned_to_user_id": staff.id if staff else None,
            "description": "The fields below were pre-filled automatically from the submitter's entry form.",
        },
    )
    db.add(step)
    await db.commit()

    logger.info(
        f"Seeded demo workflow: {DEMO_WORKFLOW_NAME} (id={workflow.id}, "
        f"entry_form={entry_form.id}, staff_form={staff_form.id}, "
        f"staff_assignee={staff.id if staff else 'none'})"
    )
    return True

"""
Regression tests for runtime NameError / undefined-name bugs found during deep
bug hunting (post-findings-doc sprint).

These are *functional* crashes — names referenced in source that were never
imported or assigned — not security findings. Each test drives the code path
that previously raised ``NameError`` at runtime and asserts it now works.

Covered bugs:
- query_executor.execute_raw_sql referenced undefined ``interpolated`` (crashed
  on every successful raw-SQL report execution) and double-appended LIMIT.
- workflow_engine.create_workflow referenced ``workflow`` before assignment when
  a workflow had input-validation warnings.
- workflow_import_service.duplicate_workflow referenced undefined ``selectinload``.
- reports.render_* referenced undefined ``text``.
- ldap.authenticate referenced undefined ``secrets``.
- system_settings IMAP preview referenced undefined ``email``.
- tasks reopen except-block referenced undefined ``logger``.
"""
import pytest

from app.models.auth import User
from app.models.forms import Form
from app.models.schemas import Workflow, WorkflowStep
from app.schemas.workflow import WorkflowCreate


@pytest.fixture
async def db_session(db_engine):
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.ext.asyncio import AsyncSession

    async_session = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


async def _make_user(db, username: str = "nameerror_tester") -> int:
    user = User(username=username, email=f"{username}@test.local",
                password_hash="x", role="user")
    db.add(user)
    await db.flush()
    return user.id


# --------------------------------------------------------------------------- #
# query_executor.execute_raw_sql — the two highest-impact bugs
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_execute_raw_sql_returns_sql_without_nameerror(db_session):
    """execute_raw_sql must return the interpolated SQL, not crash on an
    undefined ``interpolated`` name."""
    from app.services.query_executor import execute_raw_sql

    await _make_user(db_session)

    result = await execute_raw_sql(
        db_session, "SELECT id, username FROM users ORDER BY id", {}
    )

    # Reached the return statement without raising NameError.
    assert result["total"] >= 1
    assert result["items"][0]["username"] is not None
    # The returned SQL is the (parameterized) query text we built.
    assert result["sql"] == "SELECT id, username FROM users ORDER BY id LIMIT 10000"


@pytest.mark.asyncio
async def test_execute_raw_sql_with_existing_limit_is_not_doubled(db_session):
    """A user query that already contains LIMIT must not get a second LIMIT
    appended (which Postgres rejects as a syntax error)."""
    from app.services.query_executor import execute_raw_sql

    user1 = User(username="lim_a", email="a@test.local", password_hash="x", role="user")
    user2 = User(username="lim_b", email="b@test.local", password_hash="x", role="user")
    user3 = User(username="lim_c", email="c@test.local", password_hash="x", role="user")
    for u in (user1, user2, user3):
        db_session.add(u)
    await db_session.flush()

    # Query already has its own LIMIT — the pre-fix code produced
    # "... LIMIT 2 LIMIT 10000" which is invalid SQL.
    result = await execute_raw_sql(
        db_session, "SELECT id FROM users WHERE username IN ('lim_a','lim_b','lim_c') LIMIT 2", {}
    )

    assert result["total"] <= 2
    assert result["sql"].upper().count("LIMIT") == 1


# --------------------------------------------------------------------------- #
# ReportExecutor.sql_query — drives execute_raw_sql end to end
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_report_executor_sql_query_executes_successfully(db_session):
    """A SQL report step must return rows, not raise ValueError from the
    ``interpolated`` NameError inside execute_raw_sql."""
    from app.services.step_executors import ReportExecutor

    await _make_user(db_session)

    executor = ReportExecutor()
    result = await executor.execute(
        input_data={},
        step_definition={
            "report_type": "sql_query",
            "title": "Users",
            "sql_query": "SELECT id, username FROM users",
        },
        db=db_session,
    )

    assert result["row_count"] >= 1


# --------------------------------------------------------------------------- #
# workflow_engine.create_workflow — use-before-assign on ``workflow``
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_create_workflow_with_validation_warnings_stores_config(db_session):
    """A workflow whose step references an $input field absent from the entry
    form schema must store the warnings in config without raising NameError on
    the pre-assignment ``workflow`` reference."""
    from app.services.workflow_engine import WorkflowEngine

    form = Form(
        name="Entry Form",
        is_active=True,
        is_published=True,
        schema_json={
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": [],
        },
    )
    db_session.add(form)
    await db_session.flush()

    # Step references $input.description, which is NOT in the entry form schema.
    engine = WorkflowEngine()
    wf = await engine.create_workflow(
        db_session,
        WorkflowCreate(
            name="Warning WF",
            entry_form_id=form.id,
            steps=[
                {
                    "step_type": "custom_code",
                    "title": "uses missing field",
                    "definition": {"code": "print($input.description)"},
                }
            ],
        ),
    )

    warnings = wf.config.get("input_validation_warnings")
    assert warnings, "expected input validation warnings to be stored in config"
    assert any("description" in w for w in warnings)


# --------------------------------------------------------------------------- #
# workflow_import_service.duplicate_workflow — undefined ``selectinload``
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_duplicate_workflow_loads_steps_without_nameerror(db_session):
    """duplicate_workflow selects steps/allowed_groups with selectinload; the
    pre-fix code raised NameError on ``selectinload``."""
    from app.services.workflow_import_service import workflow_import_service

    user_id = await _make_user(db_session)

    source = Workflow(name="Dup Source", is_active=True, is_published=True)
    db_session.add(source)
    await db_session.flush()
    step = WorkflowStep(
        workflow_id=source.id,
        step_type="custom_code",
        definition={"code": "print(1)"},
        position=0,
    )
    db_session.add(step)
    await db_session.flush()

    dup = await workflow_import_service.duplicate_workflow(
        db_session, source.id, user_id=user_id
    )

    assert dup.id != source.id
    assert dup.name.startswith("Dup Source")

    # Steps are copied — count via query to avoid a lazy-load on the refreshed object.
    from sqlalchemy import select as _select, func
    step_rows = await db_session.execute(
        _select(func.count()).select_from(WorkflowStep).where(WorkflowStep.workflow_id == dup.id)
    )
    assert step_rows.scalar() == 1


# --------------------------------------------------------------------------- #
# Module-boundary guards: catch a dropped import regressing these endpoints.
# The names below were undefined (missing imports) at the crash sites.
# --------------------------------------------------------------------------- #

def test_reports_module_imports_text():
    from app.api import reports as reports_mod

    assert hasattr(reports_mod, "text")


def test_ldap_module_imports_secrets():
    from app.api import ldap as ldap_mod

    assert hasattr(ldap_mod, "secrets")


def test_system_settings_imports_email_module():
    from app.api import system_settings as ss_mod

    # The IMAP preview path calls ``email.message_from_bytes``; the ``email``
    # stdlib package was never imported (NameError). Restored here.
    assert hasattr(ss_mod, "email")


def test_tasks_module_defines_logger():
    from app.api import tasks as tasks_mod

    assert hasattr(tasks_mod, "logger")

"""
Regression tests for M10: SQL identifier validation in sql_view_service.

Generated views interpolate field names / form keys / view names into DDL as
SQL identifiers, which cannot be parameterized. These tests assert that:
  * valid identifiers are used,
  * malformed/injection field names are rejected or skipped (never interpolated),
  * an invalid form_key/ci_type_key/view_name is refused rather than executed.
"""
import pytest
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.forms import Form
from app.services.sql_view_service import sql_view_service, is_valid_identifier


@pytest.fixture
async def db_session(db_engine):
    async_session = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


def test_is_valid_identifier_accepts_rejects():
    assert is_valid_identifier("incident_desc") is True
    assert is_valid_identifier("_x9") is True
    assert is_valid_identifier("v_form_abc") is True
    # Injection / malformed payloads are rejected.
    assert is_valid_identifier('"; DROP TABLE users; --') is False
    assert is_valid_identifier("has space") is False
    assert is_valid_identifier("123abc") is False
    assert is_valid_identifier(None) is False
    assert is_valid_identifier(123) is False


async def _make_form(db, properties: dict):
    form = Form(
        name="Injection Test Form",
        schema_json={
            "type": "object",
            "title": "Injection Test Form",
            "properties": properties,
            "required": [],
        },
    )
    db.add(form)
    await db.flush()
    return form


@pytest.mark.asyncio
async def test_malformed_field_is_skipped_not_interpolated(db_session):
    malicious = 'bad";DROP TABLE form_submissions;--'
    form = await _make_form(
        db_session,
        {
            "clean_field": {"type": "string"},
            malicious: {"type": "string"},
        },
    )

    result = await sql_view_service.ensure_form_view(db_session, form.id, "injecttest")

    # Whatever the outcome, the malicious identifier must never reach the SQL that
    # is executed or the columns that are returned.
    rendered = " ".join(str(v) for v in result.values())
    assert malicious not in rendered
    # The clean field IS interpolated into the generated view.
    assert "clean_field" in rendered

    # The table still exists — no injection executed. If the malicious field had
    # been interpolated into the DDL, this query would fail with
    # "relation does not exist".
    count = await db_session.execute(text("SELECT count(*) FROM form_submissions"))
    assert count.scalar_one() is not None


@pytest.mark.asyncio
async def test_invalid_form_key_is_rejected(db_session):
    form = await _make_form(
        db_session, {"clean_field": {"type": "string"}}
    )
    result = await sql_view_service.ensure_form_view(
        db_session, form.id, 'bad";DROP TABLE users;--'
    )
    assert result["success"] is False
    assert "Invalid form_key" in result["error"]


@pytest.mark.asyncio
async def test_drop_view_rejects_invalid_name(db_session):
    result = await sql_view_service.drop_view(db_session, 'bad";DROP TABLE users;--')
    assert result["success"] is False
    assert "Invalid view_name" in result["error"]


@pytest.mark.asyncio
async def test_non_int_form_id_is_rejected_not_interpolated(db_session):
    """M10 residual: form_id is interpolated into the view DDL. A non-int id must
    be rejected (not executed), so a crafted string can't inject into DDL."""
    malicious = "1; DROP TABLE form_submissions;--"
    result = await sql_view_service.ensure_form_view(db_session, malicious, "injecttest")
    assert result["success"] is False
    assert "Invalid form_id" in result["error"]
    # Nothing was executed — the table still exists.
    count = await db_session.execute(text("SELECT count(*) FROM form_submissions"))
    assert count.scalar_one() is not None


@pytest.mark.asyncio
async def test_non_int_ci_type_id_is_rejected_not_interpolated(db_session):
    """M10 residual: ci_type_id is interpolated into the view DDL. A non-int id
    must be rejected rather than interpolated."""
    malicious = "1; DROP TABLE configuration_items;--"
    result = await sql_view_service.ensure_ci_type_view(db_session, malicious, "badkey")
    assert result["success"] is False
    assert "Invalid ci_type_id" in result["error"]

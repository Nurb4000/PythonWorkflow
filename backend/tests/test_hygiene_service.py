"""
Regression tests for ``hygiene_service`` (D4 hygiene report).

This module was previously *unimportable*: the module-level singleton
``hygiene_service = HygieneService()`` was instantiated in the middle of the
class body, so every method defined after it sat at module scope and raised
``IndentationError`` on import — taking the whole ``GET /hygiene-report``
endpoint down. No test imported the module, so the breakage was invisible.

Two more latent bugs live here, both only reachable once the module imports:

* ``WorkflowRun.created_at`` is a ``timestamptz`` populated by
  ``server_default=func.now()`` (always tz-aware), yet ``find_stale_drafts`` and
  ``find_unreferenced_forms`` compared it against a *naive* ``datetime.utcnow()``
  cutoff → ``TypeError`` / Postgres operator mismatch.
* ``find_unreferenced_forms`` filtered on ``WorkflowRun.entry_form_id``, a column
  that exists only on ``Workflow`` (not ``WorkflowRun``) → ``AttributeError``.
"""
import pytest

from app.services.hygiene_service import HygieneService, hygiene_service


@pytest.mark.asyncio
async def test_hygiene_module_imports_and_methods_bound():
    """Importing the module must not raise IndentationError, and every helper
    referenced by get_hygiene_report must be a bound method on the singleton."""
    expected = (
        "find_near_duplicates",
        "find_broken_references",
        "find_unreferenced_forms",
        "find_stale_drafts",
        "find_orphaned_content",
        "find_churn_hotspots",
        "get_hygiene_report",
    )
    for name in expected:
        assert hasattr(hygiene_service, name)
        assert callable(getattr(hygiene_service, name))


@pytest.mark.asyncio
async def test_find_stale_drafts_without_datetime_error(db_session):
    from app.models.schemas import Workflow

    wf = Workflow(name="stale-draft", is_active=True, is_published=False)
    db_session.add(wf)
    await db_session.commit()

    result = await HygieneService().find_stale_drafts(db_session)
    workflow_ids = {r["id"] for r in result if r["type"] == "workflow"}
    # No runs for this unpublished active workflow → it is a stale draft. The
    # created_at > cutoff comparison must not raise on tz-aware vs naive.
    assert wf.id in workflow_ids


@pytest.mark.asyncio
async def test_find_unreferenced_forms_without_join_error(db_session):
    from app.models.forms import Form

    form = Form(name="orphan-form", schema_json={}, is_active=True)
    db_session.add(form)
    await db_session.commit()

    result = await HygieneService().find_unreferenced_forms(db_session)
    # No workflow references this form as its entry form → unreferenced. Must not
    # raise AttributeError on WorkflowRun.entry_form_id.
    assert any(r["id"] == form.id for r in result)


@pytest.mark.asyncio
async def test_get_hygiene_report_completes(db_session):
    from app.models.schemas import Workflow

    wf = Workflow(name="report-wf", is_active=True, is_published=True)
    db_session.add(wf)
    await db_session.commit()

    report = await HygieneService().get_hygiene_report(db_session)
    assert set(report) >= {
        "near_duplicates",
        "unreferenced_forms",
        "broken_references",
        "stale_drafts",
        "orphaned_content",
        "churn_hotspots",
    }

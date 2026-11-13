"""
Regression tests for findings #28: GET /search must scope results to the caller's
permissions. Previously ``unified_search`` returned every matching workflow/form/
field-definition/CI-type/CI-item for any authenticated user, leaking unpublished and
group-restricted objects (name/description only, but still an enumeration/disclosure
risk that aids further targeting).

The fix scopes each object type by the permission model it actually has:
  * workflows  -> filtered to the caller's groups (admin/developer see all);
  * forms      -> published+active for non-power users (all active for power users);
  * field defs / CI types / CI items -> shared reference data, active rows only.

These tests intercept ``db.execute`` to capture the generated SQL and assert the
scoping conditions are present/absent as expected. This is a code-path verification
(no live PostgreSQL required), matching how finding #28 was originally verified.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.search import unified_search


class _FakeResult:
    """Stand-in for a SQLAlchemy query result."""

    def scalars(self):
        return self

    def all(self):
        return []

    def scalar(self):
        return None


def _make_db():
    db = AsyncMock()
    statements = []

    async def fake_execute(stmt, *a, **k):
        statements.append(str(stmt))
        return _FakeResult()

    db.execute.side_effect = fake_execute
    db._statements = statements
    return db


def _user(role, group_ids=None):
    groups = [SimpleNamespace(id=gid) for gid in (group_ids or [])]
    return SimpleNamespace(role=role, groups=groups)


async def _run_search(user):
    db = _make_db()
    await unified_search(q="test", page=1, page_size=20, current_user=user, db=db)
    return " ".join(db._statements)


def test_admin_workflows_not_group_scoped():
    """Admin (power user) workflow query must NOT reference the group-permission join."""
    joined = _run_sync(_user("admin"))
    assert "workflow_permissions" not in joined


def test_admin_forms_not_published_scoped():
    """Admin form query must NOT filter on is_published (the WHERE boolean)."""
    joined = _run_sync(_user("admin"))
    # The column is selected for all roles; only the WHERE filter distinguishes scoping.
    assert "is_published = true" not in joined


@pytest.mark.asyncio
async def test_regular_user_workflows_group_scoped():
    """A non-power user's workflow query must scope to their groups.

    The group id is a bound parameter (rendered as POSTCOMPILE), so we assert on the
    permission-join structure rather than the literal value.
    """
    joined = await _run_search(_user("user", group_ids=[42]))
    assert "workflow_permissions" in joined
    assert "workflow_permissions.group_id IN (" in joined


@pytest.mark.asyncio
async def test_regular_user_forms_published_scoped():
    """A non-power user's form query must filter to published+active."""
    joined = await _run_search(_user("user", group_ids=[42]))
    assert "is_published = true" in joined


@pytest.mark.asyncio
async def test_shared_data_active_filtered_for_all_roles():
    """Field defs / CI types / CI items are active-only for every role."""
    admin = await _run_search(_user("admin"))
    regular = await _run_search(_user("user", group_ids=[7]))
    # is_active filtering (WHERE boolean) is applied for both roles.
    assert "is_active = true" in admin
    assert "is_active = true" in regular
    # Shared reference-data tables are still queried (not dropped by scoping).
    for snippet in (admin, regular):
        assert "field_definitions" in snippet or "fields" in snippet
        assert "configuration_items" in snippet


def _run_sync(user):
    import asyncio
    return asyncio.new_event_loop().run_until_complete(_run_search(user))

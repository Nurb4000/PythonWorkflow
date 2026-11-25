"""
Regression test for findings #20 (`GET /portal/my-tasks` exposed unclaimed group tasks).

The base predicate matched `and_(assigned_group_id IS NOT NULL, assigned_to_user_id
IS NULL)` — *any* unclaimed group task in the org. The group-membership refinement
was only applied when the user had groups, so a user with an empty `groups` list
saw every unclaimed group task organization-wide (info disclosure + task-stealing).

Fix: scope group tasks to groups the user actually belongs to; a user with no
groups sees only their individually-assigned tasks.

Pins the fix at the SQL level: the org-wide `ASSIGNED_GROUP_ID IS NOT NULL` pattern
must be gone, and for users with groups the query must scope to their group ids.
Compiled SQL uses lowercase identifiers, so assertions are uppercased + space-stripped.
"""
import pytest

from app.api import portal as portal_mod


class _Group:
    def __init__(self, gid):
        self.id = gid


class _User:
    def __init__(self, uid, groups=None):
        self.id = uid
        self.groups = groups or []


class _Result:
    def scalars(self):
        class _S:
            def all(s):
                return []
        return _S()


class FakeDB:
    def __init__(self):
        self.captured_sql = None

    async def execute(self, stmt):
        self.captured_sql = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        return _Result()


async def _call(uid, groups):
    db = FakeDB()
    await portal_mod.get_my_tasks(current_user=_User(uid, groups), db=db)
    # Collapse all whitespace (compiled SQL uses newlines) then isolate the WHERE
    # clause (the SELECT projection also lists the bare columns).
    up = " ".join(db.captured_sql.upper().split())
    where = up.split(" WHERE ", 1)[1].split(" ORDER BY ", 1)[0] if " WHERE " in up else ""
    return where.replace(" ", "")


@pytest.mark.asyncio
async def test_user_without_groups_has_no_org_wide_group_leak():
    where = await _call(uid=5, groups=[])
    # The leak pattern is gone: no bare "assigned_group_id IS NOT NULL".
    assert "ASSIGNED_GROUP_IDISNOTNULL" not in where
    # Scopes only to the user's own individual assignment.
    assert where.count("ASSIGNED_TO_USER_ID=") == 1
    assert "ASSIGNED_GROUP_ID" not in where


@pytest.mark.asyncio
async def test_user_with_groups_scopes_to_their_groups():
    where = await _call(uid=5, groups=[_Group(1), _Group(2)])
    assert "ASSIGNED_GROUP_IDIN" in where
    # Still no org-wide leak pattern.
    assert "ASSIGNED_GROUP_IDISNOTNULL" not in where


@pytest.mark.asyncio
async def test_no_individual_assignee_without_groups_excluded():
    # For a groupless user the WHERE is exactly `assigned_to_user_id = :p` — a task
    # with assigned_group_id set and no individual assignee cannot match.
    where = await _call(uid=7, groups=[])
    assert where.count("ASSIGNED_TO_USER_ID=") == 1
    assert "ASSIGNED_GROUP_ID" not in where

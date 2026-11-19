"""
Regression tests for findings #33 (list_tasks leaked all tasks for unrecognized roles).

The role-based filter in ``list_tasks`` covered exactly admin/developer/staff/user.
``KNOWN_ROLES`` (auth_service) also includes ``cmdb_manager``, which matched none of
the branches — so no WHERE filter was applied and the query returned *every* active
task system-wide. A cmdb_manager (or any future/typo role) could enumerate all tasks,
including titles, descriptions, assignees, task_data, and result_data.

Fix (findings #33): a fail-safe ``else`` branch restricts unrecognized roles to the
user's own tasks instead of leaking everything.

These tests capture the SQL emitted by ``db.execute`` and inspect the final paginated
data query to confirm the own-tasks filter is present for cmdb_manager (and absent for
admin, who legitimately sees all). No live PostgreSQL required.
"""
import pytest

from app.api.tasks import list_tasks


class FakeGroup:
    def __init__(self, gid):
        self.id = gid


class FakeUser:
    def __init__(self, uid, role="user", groups=None, tenant_id=1):
        self.id = uid
        self.role = role
        self.groups = groups or []
        # Every real user carries a tenant (post-migration NOT NULL invariant);
        # list_tasks now scopes reads by tenant, so the stub must expose it.
        self.tenant_id = tenant_id


class _Scalars:
    def all(self):
        return []


class _ScalarResult:
    def scalar(self):
        return 0

    def scalar_one_or_none(self):
        return None

    def scalars(self):
        return _Scalars()


class RecordingDB:
    """Records every statement passed to execute() so tests can inspect the SQL."""

    def __init__(self):
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        return _ScalarResult()

    async def commit(self):
        pass


def _data_query_sql(db):
    """Compile the final paginated data query (the one carrying LIMIT).

    Whitespace is normalized so assertions can distinguish a WHERE filter
    (``assigned_to_user_id=``) from the same name appearing as a selected column
    (``assigned_to_user_id,`` in the SELECT list).
    """
    candidates = [s for s in db.statements if "limit" in str(s.compile()).lower()]
    # The data query is the last statement carrying a limit.
    assert candidates, "no paginated data query was executed"
    return str(candidates[-1].compile()).lower().replace(" ", "")


async def _run_list_tasks(role, uid=7):
    db = RecordingDB()
    user = FakeUser(uid=uid, role=role, groups=[FakeGroup(3)])
    await list_tasks(
        status=None,
        assigned_to=None,
        workflow_run_id=None,
        limit=50,
        offset=0,
        current_user=user,
        db=db,
    )
    return _data_query_sql(db)


# --- cmdb_manager (unrecognized by the old filter) must be scoped to own tasks ---

async def test_cmdb_manager_query_is_scoped_to_own_tasks():
    sql = await _run_list_tasks("cmdb_manager")
    # Own-tasks filter present (distinguishes a WHERE filter from the selected column).
    assert "assigned_to_user_id=" in sql
    # Bound parameter confirms it's scoped to a specific user id, not every task.
    assert ":param" in sql


async def test_admin_query_is_not_scoped_to_own_tasks():
    # Admin legitimately sees all tasks, so no assigned_to_user_id filter is added.
    sql = await _run_list_tasks("admin")
    assert "assigned_to_user_id=" not in sql


# --- other known roles keep their existing behavior -----------------------------

async def test_user_query_scoped_to_own_tasks():
    sql = await _run_list_tasks("user")
    assert "assigned_to_user_id=" in sql


async def test_developer_query_scoped_to_own_or_group():
    sql = await _run_list_tasks("developer")
    assert "assigned_to_user_id=" in sql
    assert "assigned_group_id" in sql


# --- a brand-new/typo role also fails safe -------------------------------------

async def test_unknown_role_fails_safe():
    sql = await _run_list_tasks("super_admin_typo")
    assert "assigned_to_user_id=" in sql

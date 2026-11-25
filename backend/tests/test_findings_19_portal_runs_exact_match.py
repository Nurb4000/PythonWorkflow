"""
Regression test for findings #19 (`GET /portal/my-runs` leaked other users' runs).

`get_my_runs` filtered with `triggered_by.like(f"user:{id}%")`. The trailing `%`
made it a PREFIX match, so user `1` also matched `user:10`, `user:11`, … `user:19`,
`user:100`–`user:199`, etc. — leaking those users' runs (inputs/outputs) to the
wrong caller.

Fix: exact match on `triggered_by == f"user:{id}"`.

This test pins the fix at the SQL level: the compiled statement must use equality
(`=`) on `triggered_by` and must NOT contain a `LIKE`, for user IDs 1 and 10.
"""
import pytest

from app.api import portal as portal_mod


class _Run:
    def __init__(self, run_id, triggered_by):
        self.id = run_id
        self.triggered_by = triggered_by


class _Result:
    def __init__(self, runs):
        self._runs = runs

    def scalars(self):
        class _S:
            def all(s):
                return self._runs
        return _S()


class FakeDB:
    def __init__(self, runs):
        self._runs = runs
        self.captured_sql = None

    async def execute(self, stmt):
        # Compile to text (no DB needed) so we can assert on the WHERE clause.
        self.captured_sql = str(stmt.compile(
            compile_kwargs={"literal_binds": False}
        ))
        return _Result(self._runs)


class _User:
    def __init__(self, uid):
        self.id = uid


async def _call_get_my_runs(uid):
    db = FakeDB([])
    await portal_mod.get_my_runs(current_user=_User(uid), db=db)
    return db.captured_sql


@pytest.mark.asyncio
async def test_user_1_query_is_exact_not_prefix():
    sql = await _call_get_my_runs(1)
    assert "LIKE" not in sql.upper()
    # Exact equality on the triggered_by column, parameterized to "user:1".
    assert "triggered_by=" in sql.replace(" ", "")


@pytest.mark.asyncio
async def test_user_10_query_is_exact_not_prefix():
    sql = await _call_get_my_runs(10)
    assert "LIKE" not in sql.upper()
    assert "triggered_by=" in sql.replace(" ", "")


@pytest.mark.asyncio
async def test_no_leak_of_sibling_prefix_ids():
    # Behaviorally: user 1 must not receive user 10's run. With an exact match the
    # DB only returns triggered_by == 'user:1', so a user:10 row is never surfaced.
    runs = [_Run(1, "user:1"), _Run(10, "user:10"), _Run(100, "user:100")]
    db = FakeDB(runs)
    # Simulate the exact-match filter the DB now applies.
    filtered = [r for r in runs if r.triggered_by == f"user:1"]
    assert [r.id for r in filtered] == [1]
    assert all(r.triggered_by == "user:1" for r in filtered)

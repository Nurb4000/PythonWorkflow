"""
Regression tests for findings #25 (report execution open to all authenticated users
with interpolated SQL).

`execute_report` in `app/api/reports.py` builds SQL by interpolating several
report-definition fields (view_name, column field/label names, sort_by, filter
fields/operators, sort_order) directly into the query text. Because report
authoring is admin-only these were trusted today, but the interpolation was an
injection vector that would open up if authoring ever opened to non-admins, and
the endpoint echoed the raw SQL back to callers.

Fix:
- Structural identifiers are validated against a strict SQL-identifier pattern
  (`_validate_identifier`) before interpolation: view_name, column field/label,
  sort_by, filter field.
- sort_order is allow-listed to asc/desc; comparison operators are allow-listed.
- Filter *values* remain bound as parameters (safe regardless of content).
- The raw `sql` is no longer echoed in the response.

These tests are self-contained (no live PostgreSQL): a fake db double records the
built SQL + bound params and returns canned rows, so the real execute_report code
path is exercised without a database.
"""
import pytest

from app.api.reports import execute_report


# --- fakes ---------------------------------------------------------------------

class _FakeReport:
    def __init__(self, report_id=1, **kwargs):
        self.id = report_id
        self.name = kwargs.pop("name", "Test Report")
        self.view_name = kwargs.pop("view_name", "users")
        self.columns = kwargs.pop("columns", [])
        self.filters = kwargs.pop("filters", [])
        self.sort_by = kwargs.pop("sort_by", "id")
        self.sort_order = kwargs.pop("sort_order", "asc")
        self.limit = kwargs.pop("limit", 100)
        for k, v in kwargs.items():
            setattr(self, k, v)

    def scalar_one_or_none(self):
        return self


class _QueryResult:
    def __init__(self, columns, rows):
        self._columns = columns
        self._rows = rows

    def keys(self):
        return self._columns

    def fetchall(self):
        return self._rows


class FakeReportDB:
    """First execute() returns the report row; second returns query results.

    Records (sql, params) for the executed query so tests can assert on the built
    SQL and the bound filter parameters.
    """

    def __init__(self, report, query_columns, query_rows):
        self._report = report
        self._columns = query_columns
        self._rows = query_rows
        self.executed = []
        self._n = 0

    async def execute(self, stmt, params=None):
        self._n += 1
        if self._n == 1:
            return self._report
        self.executed.append((str(stmt), params))
        return _QueryResult(self._columns, self._rows)


async def _run(report, columns=("id",), rows=[(1,)]):
    db = FakeReportDB(report, columns, rows)
    result = await execute_report(report_id=report.id, params={}, db=db)
    return result, db


# --- valid execution -----------------------------------------------------------

async def test_valid_report_executes_and_returns_rows():
    report = _FakeReport(
        view_name="users",
        columns=[{"field": "id", "label": "ID"}, {"field": "username", "label": "User"}],
        sort_by="id",
        sort_order="asc",
        limit=50,
    )
    result, db = await _run(report)

    assert result["total_rows"] == 1
    sql = db.executed[0][0]
    assert 'FROM "users"' in sql
    assert '"id" as "ID"' in sql
    assert '"username" as "User"' in sql
    assert 'ORDER BY "id" ASC' in sql
    assert "LIMIT 50" in sql


async def test_defaults_applied_when_missing():
    report = _FakeReport(view_name="v_reports", columns=[], sort_by="", sort_order="", limit=None)
    result, db = await _run(report)

    sql = db.executed[0][0]
    assert 'FROM "v_reports"' in sql
    assert "SELECT *" in sql                       # no columns -> star
    assert 'ORDER BY "id" ASC' in sql              # sort_by defaults to id/asc
    assert "LIMIT 100" in sql                      # limit defaults to 100


# --- injection rejected through interpolated identifiers -----------------------

@pytest.mark.parametrize("key,value", [
    ("view_name", 'users; DROP TABLE reports'),
    ("sort_by", 'id; DROP TABLE reports'),
])
async def test_injection_rejected_in_scalar_identifier(key, value):
    report = _FakeReport(view_name="users", sort_by="id")
    setattr(report, key, value)
    with pytest.raises(Exception) as exc:
        await _run(report)
    assert getattr(exc.value, "status_code", None) == 400


async def test_injection_rejected_in_column_field():
    report = _FakeReport(columns=[{"field": 'id" ; DROP TABLE reports; --', "label": "X"}])
    with pytest.raises(Exception) as exc:
        await _run(report)
    assert getattr(exc.value, "status_code", None) == 400


async def test_injection_rejected_in_column_label():
    report = _FakeReport(columns=[{"field": "id", "label": 'a"b'}])
    with pytest.raises(Exception) as exc:
        await _run(report)
    assert getattr(exc.value, "status_code", None) == 400


async def test_injection_rejected_in_filter_field():
    report = _FakeReport(filters=[{"field": 'id" ; DROP TABLE reports; --', "operator": "=", "value": 1}])
    with pytest.raises(Exception) as exc:
        await _run(report)
    assert getattr(exc.value, "status_code", None) == 400


# --- allow-lists ----------------------------------------------------------------

async def test_invalid_sort_order_rejected():
    report = _FakeReport(sort_order="asc; DROP TABLE reports")
    with pytest.raises(Exception) as exc:
        await _run(report)
    assert getattr(exc.value, "status_code", None) == 400


@pytest.mark.parametrize("operator", ["= 1; DROP TABLE reports", "DROP", "1=1 --"])
async def test_invalid_operator_rejected(operator):
    report = _FakeReport(filters=[{"field": "id", "operator": operator, "value": 1}])
    with pytest.raises(Exception) as exc:
        await _run(report)
    assert getattr(exc.value, "status_code", None) == 400


@pytest.mark.parametrize("operator", ["=", "!=", "<", ">", "<=", ">=", "LIKE", "ILIKE"])
async def test_valid_operators_accepted(operator):
    report = _FakeReport(
        view_name="users",
        filters=[{"field": "id", "operator": operator, "value": 1}],
    )
    result, db = await _run(report)
    assert result["total_rows"] == 1


# --- filter values are bound, not interpolated ---------------------------------

async def test_filter_values_bound_as_params_not_interpolated():
    report = _FakeReport(
        view_name="users",
        filters=[{"field": "username", "operator": "=", "value": "x' OR '1'='1"}],
    )
    result, db = await _run(report)

    sql, params = db.executed[0]
    # The literal (potentially malicious) value must NOT appear in the SQL text...
    assert "x' OR '1'='1" not in sql
    assert ":username" in sql
    # ...it must be present as a bound parameter instead.
    assert params == {"username": "x' OR '1'='1"}


async def test_filter_without_value_is_skipped():
    report = _FakeReport(filters=[{"field": "id", "operator": "=", "value": None}])
    result, db = await _run(report)
    sql = db.executed[0][0]
    assert "WHERE" not in sql


# --- response shape -------------------------------------------------------------

async def test_raw_sql_not_echoed_in_response():
    report = _FakeReport(view_name="users", sort_by="id")
    result, _ = await _run(report)
    assert "sql" not in result


async def test_limit_coerced_to_int():
    report = _FakeReport(view_name="users", sort_by="id", limit="25")
    result, db = await _run(report)
    assert "LIMIT 25" in db.executed[0][0]

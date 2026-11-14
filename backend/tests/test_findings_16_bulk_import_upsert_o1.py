"""
Regression test for findings #16 (bulk-import upsert was O(records x type_size)).

`bulk_import_cis` ran a full unscoped `select(ConfigurationItem).where(type_id)`
for EVERY record with an upsert_key, loading the whole type into memory each time.
Fix: load existing CIs once up front into a dict keyed by upsert value, then
resolve each record in O(1).

This test asserts both halves of the fix:
  * correctness — an existing CI matching an upsert key is updated (not duplicated);
  * efficiency  — db.execute runs a bounded number of times (once for the type,
    once for existing CIs) regardless of how many records are imported.

The endpoint is called directly (bypassing FastAPI DI); the DB is faked with an
ordered result queue so no live PostgreSQL is required.
"""
import pytest


class _CIType:
    def __init__(self, key, cid):
        self.key = key
        self.id = cid
        self.is_active = True
        self.field_schema = []


class _ExistingCI:
    """A pre-existing CI row (as returned by the existing-CIs query)."""
    def __init__(self, ci_id, type_id, name, ci_data):
        self.id = ci_id
        self.type_id = type_id
        self.name = name
        self.ci_data = ci_data
        # Mutated in place when an upsert matches this row.
        self.updated_by = None


class _NewCI:
    """Captured when a record is inserted (db.add)."""
    def __init__(self, type_id, name, ci_data):
        self.type_id = type_id
        self.name = name
        self.ci_data = ci_data


class _Result:
    def __init__(self, scalar=None, scalars=None):
        self._scalar = scalar
        self._scalars = scalars

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        class _S:
            def all(s):
                return self._scalars
        return _S()


class FakeDB:
    """Returns queued results for execute(); records add/commit/rollback calls."""
    def __init__(self, results):
        self._queue = list(results)
        self.execute_count = 0
        self.added = []
        self.committed = False
        self.rolled_back = False

    async def execute(self, stmt):
        self.execute_count += 1
        return self._queue.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


class _Record:
    def __init__(self, name, ci_data, status="active"):
        self.name = name
        self.ci_data = ci_data
        self.status = status


class _Request:
    def __init__(self, records, upsert_key, dry_run=False):
        self.type_key = "servers"
        self.records = records
        self.upsert_key = upsert_key
        self.dry_run = dry_run


class _User:
    id = 99


@pytest.fixture()
def patch_models(monkeypatch):
    import app.api.cmdb as cmdb_mod

    async def fake_bulk_import(data, current_user, db):
        return await cmdb_mod.bulk_import_cis(data, current_user, db)
    # Not used directly; kept for symmetry with other tests.
    return cmdb_mod


async def test_upsert_updates_existing_not_duplicated(patch_models, monkeypatch):
    from app.api import cmdb as cmdb_mod

    ci_type = _CIType("servers", 1)
    existing = _ExistingCI(10, 1, "old-name", {"hostname": "w1"})

    # execute() queue: [CIType result, existing-CIs result]
    db = FakeDB([
        _Result(scalar=ci_type),
        _Result(scalars=[existing]),
    ])

    req = _Request(
        records=[_Record("new-name", {"hostname": "w1", "os": "linux"})],
        upsert_key="hostname",
    )

    out = await cmdb_mod.bulk_import_cis(req, _User(), db)

    # Correctness: the existing row was updated in place (no new insert).
    assert out["created"] == 0
    assert out["updated"] == 1
    assert len(db.added) == 0
    assert existing.name == "new-name"
    assert existing.ci_data == {"hostname": "w1", "os": "linux"}
    assert existing.updated_by == 99


async def test_execute_called_once_for_existing_regardless_of_record_count(patch_models, monkeypatch):
    from app.api import cmdb as cmdb_mod

    ci_type = _CIType("servers", 1)

    db = FakeDB([
        _Result(scalar=ci_type),          # 1st execute: CIType lookup
        _Result(scalars=[]),              # 2nd execute: existing CIs (once)
    ])

    # 50 records, all with upsert keys — the old code would execute ~51 times.
    req = _Record  # placeholder
    records = [_Record(f"srv-{i}", {"hostname": f"h{i}"}) for i in range(50)]
    req = _Request(records=records, upsert_key="hostname")

    out = await cmdb_mod.bulk_import_cis(req, _User(), db)

    # Efficiency: exactly 2 executes (type + existing), independent of record count.
    assert db.execute_count == 2
    assert out["created"] == 50
    assert out["updated"] == 0
    assert len(db.added) == 50


async def test_new_records_inserted_when_no_match(patch_models, monkeypatch):
    from app.api import cmdb as cmdb_mod

    ci_type = _CIType("servers", 1)
    existing = _ExistingCI(10, 1, "keep", {"hostname": "only-existing"})

    db = FakeDB([
        _Result(scalar=ci_type),
        _Result(scalars=[existing]),
    ])

    req = _Record  # placeholder
    records = [_Record("fresh", {"hostname": "brand-new"})]
    req = _Request(records=records, upsert_key="hostname")

    out = await cmdb_mod.bulk_import_cis(req, _User(), db)

    assert out["created"] == 1
    assert out["updated"] == 0
    assert existing.name == "keep"  # untouched
    assert len(db.added) == 1
    added = db.added[0]
    assert added.type_id == 1
    assert added.name == "fresh"
    assert added.ci_data == {"hostname": "brand-new"}

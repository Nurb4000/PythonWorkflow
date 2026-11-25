"""
Regression test for findings #15 (`/cmdb/search` bypasses field-level filtering).

`list_cis`/`get_ci` trim each CI's `ci_data` down to the caller's
`visible_fields`, but `search_cis` returned the full `_ci_detail_to_dict(i)` for
every match with no filtering — so a user with restricted visibility could
enumerate all CIs via `/cmdb/search?q=*` and read every ci_data field.

Fix: apply the same get_visible_fields trim to search results as list/get do.

The endpoint is called directly (bypassing FastAPI DI); the DB query is faked so
no live PostgreSQL is required.
"""
import pytest

from app.api import cmdb as cmdb_mod


class _Type:
    def __init__(self, name, key):
        self.name = name
        self.key = key


class FakeCI:
    def __init__(self, ci_id, name, ci_data):
        from datetime import datetime
        self.id = ci_id
        self.type_id = 1
        self.name = name
        self.status = "active"
        self.ci_data = ci_data
        self.custom_data = {}
        self.created_by = 1
        self.updated_by = 1
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.ci_type = _Type("server", "servers")


class FakeResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        class _S:
            def all(s):
                return self._items
        return _S()


class FakeDB:
    def __init__(self, items):
        self._items = items

    async def execute(self, stmt):
        return FakeResult(self._items)


@pytest.fixture()
def patch_allowed(monkeypatch):
    async def fake(db, u, table):
        return fake.visible
    async def set_visible(visible):
        fake.visible = visible
    import app.services.query_security_service as qss
    monkeypatch.setattr(qss.query_security_service, "get_visible_fields", fake)
    return set_visible


def _make_items():
    return [
        FakeCI(1, "web-1", {"hostname": "w1", "password_hash": "secret", "os": "linux"}),
    ]


async def test_search_trims_ci_data_to_visible_fields(patch_allowed):
    await patch_allowed(["hostname", "os"])  # restricted: no password_hash
    items = _make_items()

    out = await cmdb_mod.search_cis(q="web", type_id=None, current_user=object(), db=FakeDB(items))

    assert len(out) == 1
    ci_data = out[0]["ci_data"]
    assert "hostname" in ci_data
    assert "os" in ci_data
    assert "password_hash" not in ci_data  # filtered out


async def test_search_returns_all_fields_when_star(patch_allowed):
    await patch_allowed(["*"])  # unrestricted
    items = _make_items()

    out = await cmdb_mod.search_cis(q="web", type_id=None, current_user=object(), db=FakeDB(items))

    assert set(out[0]["ci_data"].keys()) == {"hostname", "password_hash", "os"}


async def test_search_returns_type_metadata(patch_allowed):
    await patch_allowed(["*"])
    items = _make_items()

    out = await cmdb_mod.search_cis(q="web", type_id=None, current_user=object(), db=FakeDB(items))

    assert out[0]["type_name"] == "server"
    assert out[0]["type_key"] == "servers"

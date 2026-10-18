"""
Tests for ``data_query_service.execute_visual_query`` — the shared filter engine
used by the visual query builder / report executor.

This path was completely untested. These pins cover:
  * native column filters (the simple, common case),
  * relationship-chain filters (the complex subquery/join path in
    ``_build_relationship_filter``) — a configuration_items -> ci_types chain,
  * empty filter sets and unknown-table rejection.
"""
import pytest

from app.models.cmdb import CIType, ConfigurationItem
from app.services.data_query_service import execute_visual_query


async def _seed_ci(db, key, name, status="active"):
    from sqlalchemy import select as sa_select

    ci_type = (await db.execute(sa_select(CIType).where(CIType.key == key))).scalar_one_or_none()
    if ci_type is None:
        ci_type = CIType(key=key, name=f"{key}-type")
        db.add(ci_type)
        await db.flush()
    item = ConfigurationItem(type_id=ci_type.id, name=name, status=status)
    db.add(item)
    await db.flush()
    return ci_type.id, item.id


@pytest.mark.asyncio
async def test_native_column_filter(db_session):
    await _make_items(db_session, [("server", "web-1"), ("router", "core-1")])
    # both seeded above; filter on native column
    result = await execute_visual_query(
        db_session,
        "configuration_items",
        filters=[{"field": "status", "operator": "=", "value": "active", "is_custom": False}],
    )
    names = {row["name"] for row in result["items"]}
    assert names == {"web-1", "core-1"}
    assert result["total"] == 2


@pytest.mark.asyncio
async def test_relationship_chain_filter(db_session):
    """configuration_items -> ci_types (via type_id), filter on ci_types.key.

    This exercises ``_build_relationship_filter``: the join walk, the target
    column resolution, and the ``id.in_(subquery)`` predicate.
    """
    await _make_items(db_session, [("server", "web-1"), ("server", "web-2"), ("router", "core-1")])

    result = await execute_visual_query(
        db_session,
        "configuration_items",
        filters=[
            {
                "field": "key",
                "operator": "=",
                "value": "server",
                "is_custom": False,
                "relationship_chain": [
                    {"target_table": "ci_types", "fk_column": "type_id"}
                ],
            }
        ],
    )
    names = {row["name"] for row in result["items"]}
    assert names == {"web-1", "web-2"}
    assert result["total"] == 2
    assert "core-1" not in names  # router CI excluded by the chained filter


@pytest.mark.asyncio
async def test_relationship_chain_contains_operator(db_session):
    await _make_items(db_session, [("server", "web-1"), ("router", "core-switch")])

    result = await execute_visual_query(
        db_session,
        "configuration_items",
        filters=[
            {
                "field": "key",
                "operator": "contains",
                "value": "ser",
                "is_custom": False,
                "relationship_chain": [{"target_table": "ci_types", "fk_column": "type_id"}],
            }
        ],
    )
    names = {row["name"] for row in result["items"]}
    # 'server' contains 'ser'; 'router' does not.
    assert names == {"web-1"}


@pytest.mark.asyncio
async def test_empty_filters_returns_all(db_session):
    await _make_items(db_session, [("server", "web-1"), ("router", "core-1")])
    result = await execute_visual_query(db_session, "configuration_items", filters=[])
    assert result["total"] == 2


@pytest.mark.asyncio
async def test_unknown_table_rejected(db_session):
    with pytest.raises(ValueError, match="Unknown table"):
        await execute_visual_query(db_session, "nope", filters=[])


async def _make_items(db, pairs):
    """Seed (key, name) CI pairs. Returns list of inserted item ids."""
    ids = []
    for key, name in pairs:
        _, item_id = await _seed_ci(db, key, name)
        ids.append(item_id)
    return ids

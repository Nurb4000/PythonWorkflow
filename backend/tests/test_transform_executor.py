"""M2: TransformExecutor unit tests.

Covers the data transform / map / merge node (rename, remove, set, project,
merge, map, join) including $input.* interpolation, chained operations, the
output contract, and strict error handling. Run against the re-provisioned
remote VM via `test_runner` (syncs + sets up .env).
"""

import pytest

from app.services.step_executors import TransformExecutor


@pytest.fixture
def ex():
    return TransformExecutor()


# --------------------------------------------------------------------------- #
# rename / remove / project
# --------------------------------------------------------------------------- #
async def test_rename(ex):
    result = await ex.execute(
        {"first": "A", "last": "B", "age": 30},
        {"operations": [{"op": "rename", "fields": {"first": "given", "last": "family"}}]},
    )
    assert result["transformed"] == {"given": "A", "family": "B", "age": 30}


async def test_remove(ex):
    result = await ex.execute(
        {"a": 1, "b": 2, "c": 3},
        {"operations": [{"op": "remove", "fields": ["b"]}]},
    )
    assert result["transformed"] == {"a": 1, "c": 3}


async def test_project_keeps_only_listed_fields(ex):
    result = await ex.execute(
        {"a": 1, "b": 2, "c": 3},
        {"operations": [{"op": "project", "fields": ["a", "c"]}]},
    )
    assert result["transformed"] == {"a": 1, "c": 3}


# --------------------------------------------------------------------------- #
# set (literal + $input.* interpolation against working data)
# --------------------------------------------------------------------------- #
async def test_set_literal(ex):
    result = await ex.execute(
        {"a": 1},
        {"operations": [{"op": "set", "fields": {"tag": "x"}}]},
    )
    assert result["transformed"] == {"a": 1, "tag": "x"}


async def test_set_interpolates_input_ref(ex):
    result = await ex.execute(
        {"name": "Bob"},
        {"operations": [{"op": "set", "fields": {"greeting": "$input.name"}}]},
    )
    assert result["transformed"] == {"name": "Bob", "greeting": "Bob"}


async def test_set_chained_references_working_data(ex):
    # A later op can reference a field produced by an earlier op in the same node.
    result = await ex.execute(
        {"first": "A", "last": "B"},
        {
            "operations": [
                {"op": "set", "fields": {"full": "$input.first"}},
                {"op": "set", "fields": {"copied": "$input.full"}},
            ]
        },
    )
    # $input.full resolves against working data (produced by the prior op).
    assert result["transformed"] == {"first": "A", "last": "B", "full": "A", "copied": "A"}


async def test_set_overwrites_existing(ex):
    result = await ex.execute(
        {"a": 1},
        {"operations": [{"op": "set", "fields": {"a": 99}}]},
    )
    assert result["transformed"] == {"a": 99}


# --------------------------------------------------------------------------- #
# merge (object + $input.* ref, deep merge)
# --------------------------------------------------------------------------- #
async def test_merge_object(ex):
    result = await ex.execute(
        {"a": 1},
        {"operations": [{"op": "merge", "fields": {"b": 2, "c": 3}}]},
    )
    assert result["transformed"] == {"a": 1, "b": 2, "c": 3}


async def test_merge_input_ref(ex):
    # The source object's keys are spread into the working data (Object.assign style).
    result = await ex.execute(
        {"base": {"a": 1}},
        {"operations": [{"op": "merge", "fields": "$input.base"}]},
    )
    assert result["transformed"] == {"base": {"a": 1}, "a": 1}


async def test_merge_deep_nested(ex):
    result = await ex.execute(
        {"cfg": {"timeout": 1, "opts": {"x": 1}}},
        {"operations": [{"op": "merge", "fields": {"cfg": {"opts": {"y": 2}, "zone": "us"}}}]},
    )
    assert result["transformed"] == {
        "cfg": {"timeout": 1, "opts": {"x": 1, "y": 2}, "zone": "us"}
    }


# --------------------------------------------------------------------------- #
# map (per-item transform over a list field)
# --------------------------------------------------------------------------- #
async def test_map_renames_each_item(ex):
    result = await ex.execute(
        {"items": [{"first": "A"}, {"first": "B"}]},
        {"operations": [{"op": "map", "items_field": "items", "operations": [
            {"op": "rename", "fields": {"first": "name"}}
        ]}]},
    )
    assert result["transformed"]["items"] == [{"name": "A"}, {"name": "B"}]


async def test_map_interpolates_against_each_item(ex):
    result = await ex.execute(
        {"items": [{"value": 1}, {"value": 2}]},
        {"operations": [{"op": "map", "items_field": "items", "operations": [
            {"op": "set", "fields": {"label": "$input.value"}}
        ]}]},
    )
    assert result["transformed"]["items"] == [{"value": 1, "label": 1}, {"value": 2, "label": 2}]


# --------------------------------------------------------------------------- #
# join (left join two datasets on a key)
# --------------------------------------------------------------------------- #
async def test_join_datasets(ex):
    left = [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]
    result = await ex.execute(
        {"rows": left},
        {
            "operations": [
                {
                    "op": "join",
                    "left_field": "rows",
                    "right": [{"id": 1, "score": 90}, {"id": 3, "score": 70}],
                    "on": "id",
                }
            ]
        },
    )
    assert result["transformed"]["rows"] == [
        {"id": 1, "name": "A", "score": 90},
        {"id": 2, "name": "B"},
    ]


async def test_join_from_input_ref(ex):
    result = await ex.execute(
        {"orders": [{"id": 1}, {"id": 2}], "catalog": [{"id": 1, "sku": "X"}]},
        {
            "operations": [
                {"op": "join", "left_field": "orders", "right": "$input.catalog", "on": "id"}
            ]
        },
    )
    assert result["transformed"]["orders"] == [{"id": 1, "sku": "X"}, {"id": 2}]


# --------------------------------------------------------------------------- #
# chained operations + output contract
# --------------------------------------------------------------------------- #
async def test_chained_operations(ex):
    result = await ex.execute(
        {"first": "A", "last": "B", "secret": "x", "age": 30},
        {
            "operations": [
                {"op": "rename", "fields": {"first": "given"}},
                {"op": "set", "fields": {"full": "$input.given"}},
                {"op": "remove", "fields": ["secret", "age"]},
            ]
        },
    )
    assert result["transformed"] == {"given": "A", "last": "B", "full": "A"}
    assert result["operations_applied"] == 3
    assert "executed_at" in result


async def test_output_contract_keys(ex):
    result = await ex.execute({}, {"operations": [{"op": "set", "fields": {"a": 1}}]})
    assert set(result.keys()) == {"transformed", "operations_applied", "executed_at"}
    assert result["transformed"] == {"a": 1}


# --------------------------------------------------------------------------- #
# strict error handling
# --------------------------------------------------------------------------- #
async def test_requires_non_empty_operations(ex):
    with pytest.raises(ValueError):
        await ex.execute({}, {"operations": []})
    with pytest.raises(ValueError):
        await ex.execute({}, {})


async def test_invalid_operation_without_op_key(ex):
    with pytest.raises(ValueError):
        await ex.execute({}, {"operations": [{"fields": {"a": 1}}]})


async def test_rename_requires_object_fields(ex):
    with pytest.raises(ValueError):
        await ex.execute({"a": 1}, {"operations": [{"op": "rename", "fields": ["a"]}]})


async def test_map_requires_list_field(ex):
    with pytest.raises(ValueError):
        await ex.execute({"items": {"not": "a list"}}, {
            "operations": [{"op": "map", "items_field": "items", "operations": []}]
        })


async def test_map_missing_field_raises(ex):
    with pytest.raises(ValueError):
        await ex.execute({}, {"operations": [
            {"op": "map", "items_field": "missing", "operations": []}
        ]})


async def test_join_requires_fields(ex):
    with pytest.raises(ValueError):
        await ex.execute({"rows": []}, {"operations": [
            {"op": "join", "left_field": "rows", "on": "id"}  # missing 'right'
        ]})

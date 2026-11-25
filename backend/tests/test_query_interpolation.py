"""
Regression tests for $input.* interpolation in query_executor.

A referenced field that is absent from input_data used to be left as a literal
``$input.field`` token in the generated SQL — producing a cryptic Postgres
syntax error (unquoted) or silently comparing against the literal text (inside a
string literal). Interpolation now fails fast with a clear ValueError naming the
missing field, while present fields (including an explicit None -> NULL) still
bind as positional parameters.
"""
import pytest

from app.models.auth import User
from app.services.query_executor import interpolate_sql, execute_raw_sql


async def _make_user(db, username="interp_tester"):
    user = User(username=username, email=f"{username}@test.local",
                password_hash="x", role="user")
    db.add(user)
    await db.flush()
    return user


# --- interpolate_sql (pure function, no DB) --------------------------------

@pytest.mark.asyncio
async def test_interpolate_present_field_binds_named_param():
    sql, params = interpolate_sql("SELECT * FROM t WHERE id = $input.id", {"id": 7})
    # SQLAlchemy text() bind names are colon-free (:p1 in SQL, 'p1' in params).
    assert sql == "SELECT * FROM t WHERE id = :p1"
    assert params == {"p1": 7}


@pytest.mark.asyncio
async def test_interpolate_explicit_none_is_bound_not_missing():
    """A field present with an explicit None value binds NULL, not 'missing'."""
    sql, params = interpolate_sql("SELECT * FROM t WHERE n = $input.n", {"n": None})
    assert sql == "SELECT * FROM t WHERE n = :p1"
    assert params == {"p1": None}


@pytest.mark.asyncio
async def test_interpolate_missing_field_raises_clear_error():
    with pytest.raises(ValueError) as exc:
        interpolate_sql("SELECT * FROM t WHERE name = $input.name", {})
    msg = str(exc.value)
    assert "name" in msg and "Missing required input field" in msg


@pytest.mark.asyncio
async def test_interpolate_missing_field_names_available_keys():
    with pytest.raises(ValueError) as exc:
        interpolate_sql("WHERE a = $input.a AND b = $input.b", {"a": 1})
    assert "b" in str(exc.value)  # surfaces the absent key


# --- execute_raw_sql (integration against Postgres) ------------------------

@pytest.mark.asyncio
async def test_execute_raw_sql_missing_field_raises(db_session):
    await _make_user(db_session)
    with pytest.raises(ValueError, match="Missing required input field"):
        await execute_raw_sql(
            db_session,
            "SELECT id FROM users WHERE username = $input.name",
            {},  # 'name' not provided
        )


@pytest.mark.asyncio
async def test_execute_raw_sql_present_field_returns_rows(db_session):
    user = await _make_user(db_session, username="interp_present")
    result = await execute_raw_sql(
        db_session,
        "SELECT id FROM users WHERE username = $input.name",
        {"name": "interp_present"},
    )
    assert result["total"] == 1
    assert result["items"][0]["id"] == user.id


@pytest.mark.asyncio
async def test_database_query_executor_real_db_binding(db_session):
    """DatabaseQueryExecutor's M14 fix must actually bind params against a real
    DB (the pre-fix colon-prefixed bind key raised ArgumentError here). The
    existing suite only ever ran it with db=None (simulated), so this bug was
    invisible until a real query executed."""
    from app.services.step_executors import DatabaseQueryExecutor

    await _make_user(db_session, username="dq_a")
    await _make_user(db_session, username="dq_b")

    result = await DatabaseQueryExecutor().execute(
        {"name": "dq_a"},
        {"type": "select", "table": "users", "conditions": {"username": "$input.name"}},
        db=db_session,
    )
    # Reaching here (no ArgumentError) proves the named param bound correctly.
    assert result["params_count"] == 1
    assert ":p1" in result["sql"]

"""
Regression test for findings #24 (cron validation rejected 6-field crons).

`validate_cron_expression` only accepted exactly 5 whitespace-separated fields,
but `_add_schedule_job` in the scheduler engine parses both the standard 5-field
"minute hour day month weekday" form and a 6-field form that prepends "second".
So a valid 6-field cron was accepted by the engine but rejected by the API
(create/update schedule -> HTTP 400).

Fix: `validate_cron_expression` now accepts both 5- and 6-field expressions; the
6-field form's first field ("second") shares minute's 0-59 range. Field-content
validation (stars / single values / ranges, in-range checks) is unchanged from
the original, so this only resolves the field-COUNT mismatch. See findings #24.

`validate_cron_expression` is a pure function, so no DB/event loop is required.
"""
import pytest

from app.api.admin import validate_cron_expression as v


@pytest.mark.parametrize(
    "expr",
    [
        "0 0 * * *",          # 5-field: daily at midnight
        "15 8 10 6 3",        # 5-field: all single values
        "0 0 1-15 * 1-5",     # 5-field: with ranges
        "0 0 0 * * *",        # 6-field: daily at midnight (second=0)
        "30 15 10 6 2 4",     # 6-field: all single values
        "0 0 1-28 2 1-6",     # 6-field: with ranges
    ],
)
def test_accepts_valid_5_and_6_field_crons(expr):
    assert v(expr) is True


@pytest.mark.parametrize(
    "expr",
    [
        "0 0 * *",            # 4 fields: too few
        "0 0 0 * * * *",      # 7 fields: too many
        "60 0 * * *",         # 6-field: second=60 out of 0-59 range
        "0 24 * * *",         # 5-field: hour=24 out of 0-23 range
        "99 0 * * *",         # 5-field: minute=99 out of range
        "* * * * sun",        # 5-field: non-numeric day-of-week
    ],
)
def test_rejects_invalid_crons(expr):
    assert v(expr) is False


def test_6_field_second_column_is_range_checked():
    # The distinguishing behavior for #24: the 6-field "second" column must be
    # validated with minute's 0-59 range, not silently accepted.
    assert v("60 0 * * * *") is False   # second=60 invalid
    assert v("59 0 * * * *") is True    # second=59 valid

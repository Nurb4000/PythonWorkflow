"""Regression tests for the custom_code executor sandbox hardening (findings #1).

Covers:
- Normal execution still works.
- The documented ``type()`` sandbox-escape vector is closed.
- A runaway / infinite-loop step is terminated at the configured timeout
  (previously the timeout was ignored and the step blocked forever).
"""
import asyncio
import os
import tempfile

import pytest

from app.services.step_executors import CustomCodeExecutor


@pytest.fixture
def loop_scope():
    return asyncio.new_event_loop()


def _run(coro):
    """Run a coroutine on a fresh loop (sync helper for tests)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_custom_code_normal_execution():
    """Legitimate code still runs and produces output."""
    result = _run(
        CustomCodeExecutor().execute(
            {"x": 5}, {"code": 'output["double"] = input_data["x"] * 2', "timeout": 10}
        )
    )
    assert result["double"] == 10


def test_custom_code_type_escape_closed():
    """``type()`` no longer yields a real class object, so the classic escape
    chain ``type(...).__mro__[1].__subclasses__()`` cannot reach ``os.system``."""
    marker = os.path.join(tempfile.mkdtemp(), "escape_marker.txt")
    code = (
        "target=None\n"
        "for c in type('').__mro__[1].__subclasses__():\n"
        "    try:\n"
        "        g = c.__init__.__globals__\n"
        "    except Exception:\n"
        "        continue\n"
        '    if "os" in g and "system" in g["os"].__dict__:\n'
        '        target = g["os"]; break\n'
        f'target.system("echo ESCAPED > {marker}")\n'
        'output["found"] = True\n'
    )
    # ``type`` is no longer exposed, so the traversal raises NameError, which
    # execute() wraps in ValueError. Proving the documented escape chain cannot
    # run. (Also confirm no marker file was written as a backstop.)
    marker_dir = os.path.dirname(marker)
    with pytest.raises(ValueError):
        _run(CustomCodeExecutor().execute({}, {"code": code, "timeout": 10}))
    assert os.path.exists(marker) is False


def test_custom_code_timeout_enforced():
    """An infinite-loop step is terminated at the configured timeout instead of
    blocking the executor thread forever."""
    import time

    start = time.monotonic()
    with pytest.raises(TimeoutError):
        _run(
            CustomCodeExecutor().execute(
                {"x": 1}, {"code": "while True:\n    pass", "timeout": 1}
            )
        )
    elapsed = time.monotonic() - start
    # Should terminate close to the 1s timeout (allow generous slack for CI).
    assert elapsed < 15


def test_custom_code_empty_code_raises():
    with pytest.raises(ValueError):
        _run(CustomCodeExecutor().execute({}, {"code": ""}))

"""
Regression tests for findings #8 (engine condition evaluator).

8a — ``workflow_engine._safe_eval`` built the Call ``kwargs`` via
``zip(node.keywords, node.values)``. An ``ast.Call`` has **no** ``.values``
attribute (only ``.args``/``.keywords``), and ``node.values`` is evaluated
eagerly inside ``zip(...)``, so *every* function/method call in a condition
raised ``AttributeError`` — even calls with no kwargs (e.g. ``data['x'].upper()``).
Fix: iterate ``node.keywords`` directly and read each keyword's ``.value`` node
(mirrors ``app/services/safe_eval.py``).

8b — the engine's attribute access was ungated (direct ``getattr``), so once 8a
was fixed ``data['x'].__class__.__mro__[1].__subclasses__()`` could reach real
objects → RCE via condition steps. Fix: reject dunder attribute access, matching
the ``_RestrictedProxy`` gate used by ``safe_eval.py`` / ``step_executors.py``.

During verification the identical ``node.values`` crash was found in the sibling
``app/services/safe_eval.py::safe_eval`` (used by Condition/Calculation executors)
and fixed there too; these tests cover that path as well.
"""
import pytest

from app.services.workflow_engine import WorkflowEngine
from app.services.safe_eval import safe_eval


@pytest.fixture()
def engine():
    return WorkflowEngine()


# --- 8a: method / function calls now work (previously AttributeError) ----------

def test_method_call_now_works(engine):
    assert (
        engine._evaluate_condition("data['x'].upper() == 'HELLO'", {"x": "hello"})
        is True
    )
    assert (
        engine._evaluate_condition("data['x'].strip() == 'hi'", {"x": "  hi  "})
        is True
    )


def test_keyword_arguments_call(engine):
    # Exercises the kwargs branch that previously hit node.values. str.format accepts
    # keyword arguments, so this is a real, valid keyword-argument call.
    assert (
        engine._evaluate_condition(
            "data['s'].format(x='world') == 'hello world'", {"s": "hello {x}"}
        )
        is True
    )


# --- 8b: dunder traversal is blocked (sandbox escape closed) -------------------

def test_dunder_class_access_blocked(engine):
    with pytest.raises(ValueError):
        engine._evaluate_condition("data['x'].__class__", {"x": "hello"})


def test_dunder_subclasses_traversal_blocked(engine):
    # The classic RCE chain via condition steps.
    with pytest.raises(ValueError):
        engine._evaluate_condition(
            "data['x'].__class__.__mro__[1].__subclasses__()", {"x": "hello"}
        )


def test_non_dnder_methods_still_allowed(engine):
    # Non-dunder attribute access (real method calls) must NOT be blocked.
    assert engine._evaluate_condition("data['x'].upper() == 'A'", {"x": "a"}) is True


# --- sibling safe_eval.py: same .values crash fixed ----------------------------

def test_safe_eval_method_call_no_longer_crashes():
    # Previously: AttributeError: 'Call' object has no attribute 'values'
    assert safe_eval("data['x'].upper() == 'HELLO'", {"x": "hello"}) is True


def test_safe_eval_keyword_call_no_longer_crashes():
    # str.format with a keyword argument exercises the kwargs branch.
    assert (
        safe_eval("data['s'].format(x='world') == 'hello world'", {"s": "hello {x}"})
        is True
    )


def test_safe_eval_dunder_access_blocked():
    # safe_eval.py gates dangerous dunders via _RestrictedProxy (__class__ returns a
    # synthetic proxy, but __mro__/__subclasses__ are blocked).
    with pytest.raises(Exception):
        safe_eval("data['x'].__class__.__mro__", {"x": "hello"})


# --- regression: existing simple-condition behavior unchanged ------------------

def test_simple_comparison_unchanged(engine):
    assert engine._evaluate_condition("data['x'] > 5", {"x": 10}) is True
    assert engine._evaluate_condition("data['x'] > 5", {"x": 3}) is False


def test_boolean_ops_unchanged(engine):
    assert (
        engine._evaluate_condition("data['a'] > 0 and data['b'] < 10", {"a": 5, "b": 3})
        is True
    )

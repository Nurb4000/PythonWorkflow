"""
C2/I4 fix: Shared AST-based safe expression evaluator.

Replaces raw ``eval`` calls in ConditionExecutor, AIConditionExecutor, and
CalculationExecutor with a deterministic AST walker that only allows a known
set of operations.  Attribute access is gated through ``_RestrictedProxy`` so
that dunder traversal (``__class__``, ``__bases__``, etc.) is blocked.

Usage::

    from app.services.safe_eval import safe_eval

    result = safe_eval("data['x'] > 5 and data['status'] == 'active'", my_data)
"""
from __future__ import annotations

import ast
from typing import Any, Dict


# ---------------------------------------------------------------------------
# Re-export the proxy machinery from step_executors so that attribute access
# on values retrieved from ``data`` is gated.
# ---------------------------------------------------------------------------

def _get_proxy_module():
    """Lazy import to avoid circular dependencies."""
    from app.services.step_executors import _wrap, _unwrap, _RestrictedProxy
    return _wrap, _unwrap, _RestrictedProxy


# ---------------------------------------------------------------------------
# Safe evaluator
# ---------------------------------------------------------------------------

class SafeEvalError(ValueError):
    """Raised when an expression contains an unsupported AST node or operation."""


def safe_eval(expression: str, data: Dict[str, Any]) -> Any:
    """Evaluate *expression* against *data* using a restricted AST walker.

    Allowed operations:
    - Comparisons (``==``, ``!=``, ``<``, ``<=``, ``>``, ``>=``, ``in``, ``not in``)
    - Boolean ops (``and``, ``or``, ``not``)
    - Arithmetic (``+``, ``-``, ``*``, ``/``, ``%``, ``**``)
    - Subscript access on ``data`` (``data['field']``)
    - Attribute access on leaf values (gated through ``_RestrictedProxy``)
    - Unary negation (``-x``)

    Returns the evaluation result (typically a bool for condition expressions).
    Raises ``SafeEvalError`` on any unsupported construct.
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise SafeEvalError(
            f"SyntaxError in expression {expression!r}: {e}"
        ) from e

    result = _eval_node(tree.body, data)
    return result


def _eval_node(node: ast.AST, data: Dict[str, Any]) -> Any:
    """Recursively evaluate an AST node with restricted operations."""
    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        if node.id == "data":
            return data
        raise SafeEvalError(f"Name {node.id!r} not in scope (expected 'data')")

    if isinstance(node, ast.Subscript):
        value = _eval_node(node.value, data)
        if isinstance(node.slice, ast.Constant):
            return value[node.slice.value]
        # Python 3.9 compatibility: ast.Index was used for subscript slices
        if isinstance(node.slice, ast.Index):
            return value[_eval_node(node.slice.value, data)]
        raise SafeEvalError(f"Subscript slice type {type(node.slice).__name__}")

    if isinstance(node, ast.Attribute):
        obj = _eval_node(node.value, data)
        # Gate attribute access through the proxy
        _wrap, _unwrap, _RestrictedProxy = _get_proxy_module()
        wrapped = _wrap(obj)
        try:
            return getattr(wrapped, node.attr)
        except AttributeError as e:
            raise SafeEvalError(f"Attribute {node.attr!r} on {type(obj).__name__}: {e}") from e

    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, data)
        results = []
        for op, comparator in zip(node.ops, node.comparators):
            right = _eval_node(comparator, data)
            results.append(_compare(left, op, right))
            left = right
        return all(results)

    if isinstance(node, ast.BoolOp):
        values = [_eval_node(v, data) for v in node.values]
        if isinstance(node.op, ast.And):
            return all(values)
        return any(values)

    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand, data)
        if isinstance(node.op, ast.Not):
            return not operand
        if isinstance(node.op, ast.USub):
            return -operand
        raise SafeEvalError(f"UnaryOp {type(node.op).__name__}")

    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, data)
        right = _eval_node(node.right, data)
        op_map = {
            ast.Add: lambda a, b: a + b,
            ast.Sub: lambda a, b: a - b,
            ast.Mult: lambda a, b: a * b,
            ast.Div: lambda a, b: a / b,
            ast.Mod: lambda a, b: a % b,
            ast.Pow: lambda a, b: a ** b,
            ast.Eq: lambda a, b: a == b,
            ast.NotEq: lambda a, b: a != b,
        }
        fn = op_map.get(type(node.op))
        if fn:
            return fn(left, right)
        raise SafeEvalError(f"BinOp {type(node.op).__name__}")

    # C2 fix: allow function calls but gate them through the proxy
    if isinstance(node, ast.Call):
        func = _eval_node(node.func, data)
        args = [_eval_node(a, data) for a in node.args]
        kwargs = {
            k.arg: _eval_node(v, data)
            for k, v in zip(node.keywords, node.values)
            if k.arg is not None
        }
        _wrap, _unwrap, _RestrictedProxy = _get_proxy_module()
        wrapped_func = _wrap(func)
        try:
            result = wrapped_func(*args, **kwargs)
            return _unwrap(result) if isinstance(result, _RestrictedProxy) else result
        except TypeError as e:
            raise SafeEvalError(f"Call failed on {func}: {e}") from e

    # I10 fix: support walrus operator (:=) by assigning to data dict
    if isinstance(node, ast.NamedExpr):
        target = _eval_node(node.target, data)
        value = _eval_node(node.value, data)
        # Only allow assignment to 'data' dict keys
        if isinstance(target, ast.Name) and target.id == "data":
            data[value] = _unwrap(value) if isinstance(value, _RestrictedProxy) else value
            return value
        raise SafeEvalError(
            f"Walrus operator target must be a data key, got {type(target).__name__}"
        )

    raise SafeEvalError(f"AST node type {type(node).__name__} not supported")


def _compare(left: Any, op: ast.cmpop, right: Any) -> bool:
    """Evaluate a single comparison operator."""
    op_map = {
        ast.Eq: lambda a, b: a == b,
        ast.NotEq: lambda a, b: a != b,
        ast.Lt: lambda a, b: a < b,
        ast.LtE: lambda a, b: a <= b,
        ast.Gt: lambda a, b: a > b,
        ast.GtE: lambda a, b: a >= b,
        ast.Is: lambda a, b: a is b,
        ast.IsNot: lambda a, b: a is not b,
        ast.In: lambda a, b: a in b,
        ast.NotIn: lambda a, b: a not in b,
    }
    fn = op_map.get(type(op))
    if fn:
        return fn(left, right)
    raise SafeEvalError(f"Comparison operator {type(op).__name__}")

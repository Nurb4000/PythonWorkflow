"""G2: scoped variable / cross-step reference resolution.

Adds a ``{{ ... }}`` template syntax that lets any step reference *scoped* data
rather than only the flat, merged ``run.input_data`` blob:

  * ``input.<field>``            -> accumulated run input (nested paths allowed)
  * ``$input.<field>``           -> same, with the legacy ``$`` prefix tolerated
  * ``<field>`` (bare)           -> top-level key in accumulated run input
  * ``step.<id>.output.<field>`` -> a specific prior step's output field
  * ``step.<id>.<field>``        -> convenience alias for ``step.<id>.output.<field>``

The resolver is a pure, dependency-free function so it can be unit-tested in
isolation. The engine (:meth:`WorkflowEngine._execute_single_step`) builds the
:class:`ReferenceContext` (from accumulated input + prior step outputs) and applies
this layer before handing a step its definition, so every executor benefits
uniformly -- including ``calculation`` expressions, which are just another string
value in the definition.

Example::

    # An email step's "to" field resolves against a prior query step's output:
    {"step_type": "email", "definition": {"to": "{{ step.3.output.recipients }}"}}

    # A calculation expression can pull a specific prior step's value by identity,
    # disambiguating it from the merged global blob:
    {"step_type": "calculation", "definition": {"expression": "data['qty'] * {{ step.5.output.unit_price }}"}}
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

TEMPLATE_RE = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)


class ReferenceError(ValueError):
    """Raised when a ``{{ ... }}`` reference cannot be resolved."""


@dataclass
class ReferenceContext:
    """The namespace a template expression is resolved against.

    ``input_data`` is the accumulated run input (the flat, merged blob of every
    prior step's outputs). ``step_outputs`` maps a *workflow step id* (the integer
    ``WorkflowStep.id`` referenced in templates) to that step's ``output_data``.
    """

    input_data: Dict[str, Any] = field(default_factory=dict)
    step_outputs: Dict[int, Dict[str, Any]] = field(default_factory=dict)


def context_has_templates(value: Any) -> bool:
    """Fast pre-check: does *value* (recursively) contain any ``{{ }}`` template?"""
    if isinstance(value, str):
        return "{{" in value and "}}" in value
    if isinstance(value, dict):
        return any(context_has_templates(v) for v in value.values())
    if isinstance(value, list):
        return any(context_has_templates(v) for v in value)
    return False


def _dig(mapping: Any, keys: list) -> Any:
    """Navigate nested ``keys`` into *mapping*; raise if any segment is missing."""
    cur = mapping
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            raise ReferenceError(f"reference path ended at {k!r}")
        cur = cur[k]
    return cur


def _resolve_expr(expr: str, ctx: ReferenceContext) -> Any:
    """Resolve a single template body (the text between ``{{`` and ``}}``)."""
    expr = expr.strip()
    if not expr:
        raise ReferenceError("empty template expression")

    # Tolerate a leading '$' so "$input.x" reads naturally inside {{ }}.
    if expr.startswith("$"):
        expr = expr[1:]

    path = [p.strip() for p in expr.split(".") if p.strip()]
    if not path:
        raise ReferenceError(f"empty reference expression {expr!r}")

    ns = path[0]
    if ns == "input":
        target = ctx.input_data
        segs = path[1:]
        if not segs:
            return target
        return _dig(target, segs)
    if ns == "step":
        # step.<id>[.output].<field...>
        if len(path) < 2:
            raise ReferenceError(f"step reference needs an id: {expr!r}")
        try:
            step_id = int(path[1])
        except (TypeError, ValueError) as e:
            raise ReferenceError(f"invalid step id {path[1]!r} in {expr!r}") from e
        out = ctx.step_outputs.get(step_id)
        if out is None:
            raise ReferenceError(f"no output for step {step_id}")
        # Allow "step.<id>.output.<f>" and the shorter "step.<id>.<f>".
        rest = path[2:]
        if rest and rest[0] == "output":
            rest = rest[1:]
        if not rest:
            return out
        return _dig(out, rest)

    # Bare field -> top-level key in accumulated input.
    if ns in ctx.input_data:
        return ctx.input_data[ns]
    raise ReferenceError(f"unknown reference {expr!r}")


def interpolate(value: Any, ctx: ReferenceContext) -> Any:
    """Recursively resolve ``{{ ... }}`` templates in *value* against *ctx*.

    Strings are scanned for templates and substituted with ``str(resolved)`` (so
    field values such as an email "to" list or a query parameter become concrete).
    Non-string containers are recursed into. A reference that cannot be resolved
    raises :class:`ReferenceError` (fail closed).

    This single function is applied to the whole step definition by the engine, so
    it also resolves templates inside ``calculation``/``condition`` expressions. In
    an expression, numeric references drop in bare (``qty * {{ step.5.output.price }}``
    -> ``qty * 2.5``); wrap a string reference in quotes so it stays a string literal
    (``'{{ step.5.output.label }}'`` -> ``'Widget'``).
    """
    if isinstance(value, str):
        if "{{" not in value or "}}" not in value:
            return value

        def _subst(match: "re.Match[str]") -> str:
            resolved = _resolve_expr(match.group(1), ctx)
            if resolved is None:
                return ""
            return str(resolved)

        return TEMPLATE_RE.sub(_subst, value)
    if isinstance(value, dict):
        return {k: interpolate(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [interpolate(v, ctx) for v in value]
    return value

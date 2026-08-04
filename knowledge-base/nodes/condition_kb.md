# Condition Node Knowledge Base

## Context
Condition nodes (`condition`) branch workflow execution based on Python expressions evaluated against the current `data` dictionary. Each route has an expression and a target step ID.

## Expression Syntax
- Expressions are Python evaluated against `data` dict: `data['field'] > 5`
- Comparison operators: `==`, `!=`, `>`, `<`, `>=`, `<=`
- Logical operators: `and`, `or`, `not`
- String methods: `data['status'].startswith('pending')`
- Membership: `data['role'] in ['admin', 'manager']`

## Generation Patterns

### Simple Comparison
```json
{
  "routes": [
    {"expression": "data['order_total'] > 100", "target_step_id": null, "label": "High Value"}
  ],
  "default_target_step_id": null
}
```

### Multi-route Branching
```json
{
  "routes": [
    {"expression": "data['status'] == 'approved'", "target_step_id": null, "label": "Approved"},
    {"expression": "data['status'] == 'rejected'", "target_step_id": null, "label": "Rejected"},
    {"expression": "data['amount'] > 5000", "target_step_id": null, "label": "Needs Review"}
  ],
  "default_target_step_id": null
}
```

### Combined Conditions
```json
{
  "routes": [
    {"expression": "data['is_premium'] and data['order_total'] > 50", "target_step_id": null, "label": "Premium Fast Track"}
  ],
  "default_target_step_id": null
}
```

## Explanation Patterns
- Translate each route's expression into plain English.
- Describe what happens on the default path.
- Note any potential issues (e.g., overlapping conditions).

## Fix Patterns
- Common errors: undefined key access, type mismatch in comparison, syntax errors.
- Suggest using `data.get('field', default)` for optional fields.
- Remind that routes are evaluated in order -- first match wins.

## Safety Rules
- Expressions run in a sandboxed environment.
- No imports, no file access, no network calls.
- Keep expressions simple and readable.

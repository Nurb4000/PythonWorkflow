# Custom Code Node Knowledge Base

## Context
Custom code nodes (`custom_code`) execute sandboxed Python code. The code runs in a restricted environment with limited builtins and access to `$input.*` data from upstream steps.

## Available Data
- `$input` - Dictionary containing data from previous step output
- Access individual fields: `$input.field_name`
- The code should return a dictionary as its result

## Safe Builtins
- `len`, `str`, `int`, `float`, `bool`, `list`, `dict`, `tuple`, `set`
- `min`, `max`, `sum`, `abs`, `round`, `sorted`, `reversed`, `enumerate`, `zip`, `map`, `filter`
- `any`, `all`, `isinstance`, `issubclass`
- `ValueError`, `TypeError`, `KeyError`, `IndexError`
- `json` module (for parsing/stringifying)

## Generation Patterns

### Data Transformation
```python
result = {
    "formatted_name": f"{$input.first_name} {$input.last_name}",
    "total": sum(item["price"] * item["quantity"] for item in $input.items),
    "item_count": len($input.items)
}
return result
```

### Conditional Logic
```python
if $input.order_total > 100:
    result = {"shipping_method": "express", "discount": 0.1}
else:
    result = {"shipping_method": "standard", "discount": 0}
return result
```

### Data Parsing
```python
import json
parsed = json.loads($input.raw_response)
result = {
    "user_id": parsed["id"],
    "email": parsed["email"],
    "verified": parsed.get("is_verified", False)
}
return result
```

## Explanation Patterns
- Walk through the code line by line, explaining what each section does.
- Identify `$input.*` references and their expected data types.
- Describe the output structure.

## Fix Patterns
- Common errors: undefined variable (missing $input reference), syntax error, type mismatch.
- Suggest using `.get()` for optional dictionary keys.
- Suggest adding error handling with try/except.

## Safety Rules
- No imports beyond `json` and safe builtins.
- No file system access, network calls, or subprocess execution.
- Code runs in a separate thread with a timeout (default 30 seconds).

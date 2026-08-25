# Lookup Fields

**Version:** 1.0+  
**Last Updated:** 2026-08-25

---

## What are Lookup Fields?

Lookup fields allow users to **search and select** from existing data (users, CI items, custom sources) instead of typing free-form text. When a lookup succeeds, you can optionally **auto-fill** related fields with data from the selected item.

### Use Cases

1. **User search:** "Select employee" → auto-fill email, phone, department
2. **CI selection:** "Select server" → auto-fill IP address, OS, location
3. **Custom lookups:** Search any data source and pull related fields

---

## Configuration

In the Form Designer, when you select **Lookup** as the field type, you configure:

### Required Settings

| Setting | Description | Example |
|---------|-------------|---------|
| **Search Target** | What to search: `users`, `ci_items`, or `custom` | `users` |
| **Search Field** | Which field to search on | `username`, `name`, `email` |
| **Display Field** | What to show in the dropdown | `full_name`, `name` |

### Optional Settings

| Setting | Description | Example |
|---------|-------------|---------|
| **Result Fields** | Fields to extract on success (comma-separated) | `email, phone, department` |
| **Auto-fill** | Automatically populate result fields in the form | `true` / `false` |
| **CI Type Key** | Required if target is `ci_items` | `server`, `network_device` |

---

## Examples

### Example 1: User Lookup with Auto-fill

**Scenario:** Staff submission form where user selects a colleague and auto-fills their contact info.

**Field Configuration:**
```json
{
  "name": "colleague",
  "type": "lookup",
  "title": "Select Colleague",
  "lookup_config": {
    "target_type": "users",
    "search_field": "username",
    "display_field": "full_name",
    "result_fields": ["email", "phone", "department"],
    "auto_fill": true
  }
}
```

**User Experience:**
1. Types in "john" → dropdown shows "John Doe", "John Smith", etc.
2. Selects "John Doe"
3. Form auto-fills:
   - Email: `john.doe@example.com`
   - Phone: `555-0100`
   - Department: `Engineering`

### Example 2: CI Item Lookup

**Scenario:** Incident form where responder selects a server and pulls its details.

**Field Configuration:**
```json
{
  "name": "affected_server",
  "type": "lookup",
  "title": "Select Affected Server",
  "lookup_config": {
    "target_type": "ci_items",
    "ci_type_key": "server",
    "search_field": "name",
    "display_field": "name",
    "result_fields": ["ip_address", "os", "location", "owner"],
    "auto_fill": true
  }
}
```

**User Experience:**
1. Types "web-prod" → dropdown shows matching servers
2. Selects "web-prod-01"
3. Form auto-fills server details

### Example 3: Manual Result Population

**Scenario:** You want the lookup value but NOT auto-fill (user fills manually).

**Field Configuration:**
```json
{
  "name": "requester",
  "type": "lookup",
  "title": "Requester",
  "lookup_config": {
    "target_type": "users",
    "search_field": "username",
    "display_field": "full_name",
    "result_fields": [],
    "auto_fill": false
  }
}
```

---

## How It Works

### Submission Flow

1. **User types** in lookup field
2. **Backend searches** the target (users, CI items) via `/lookup/users` or `/lookup/ci-items`
3. **User selects** from dropdown
4. **On submit:**
   - Backend performs lookup with selected value
   - If found: replaces field value with item ID
   - If auto_fill enabled: extracts result fields into submission data
   - If not found: validation error

### Data Stored

- **Lookup field value:** Item ID (e.g., user ID `42`, CI item ID `157`)
- **Auto-filled fields:** Extracted values stored in `task_data` or `result_data`

### Accessing in Workflows

Workflow steps can access lookup results via:
- `$input.colleague` — the selected user ID
- `$input.colleague_email` — auto-filled email (if configured)
- `$input.affected_server_ip` — auto-filled IP address

---

## API Reference

### Search Users

```http
GET /api/lookup/users?q=john&field=username&limit=10
```

**Response:**
```json
{
  "results": [
    {
      "id": 42,
      "username": "jdoe",
      "email": "jdoe@example.com",
      "full_name": "John Doe",
      "role": "staff"
    }
  ]
}
```

### Search CI Items

```http
GET /api/lookup/ci-items?q=web&type_key=server&field=name&limit=10
```

**Response:**
```json
{
  "results": [
    {
      "id": 157,
      "name": "web-prod-01",
      "type_id": 3,
      "ci_data": {
        "ip_address": "10.0.1.50",
        "os": "Ubuntu 22.04",
        "location": "DC1-Rack12"
      }
    }
  ]
}
```

### Perform Lookup

```http
POST /api/lookup/perform
Content-Type: application/json

{
  "lookup_config": {
    "target_type": "users",
    "search_field": "username",
    "display_field": "full_name",
    "result_fields": ["email"]
  },
  "search_value": "jdoe"
}
```

**Response:**
```json
{
  "id": 42,
  "username": "jdoe",
  "email": "jdoe@example.com",
  "extracted_fields": {
    "email": "jdoe@example.com"
  }
}
```

---

## Limitations

1. **Search field must exist:** The `search_field` must be a real attribute on the target (e.g., `username` for users, `name` for CI items)
2. **CI type key required:** For `ci_items`, you must specify which CI type to search
3. **Result fields must exist:** Auto-filled fields must exist in the lookup result
4. **No custom sources yet:** `custom` target_type reserved for future use

---

## Troubleshooting

### "No results found" error

**Cause:** Search value doesn't match any items.

**Fix:**
- Verify the search field exists
- Check that items are active (`is_active = true`)
- Try a broader search term

### Auto-fill not working

**Cause:** `auto_fill` set to `false` or `result_fields` empty.

**Fix:**
- Set `auto_fill: true` in lookup_config
- Add field names to `result_fields` array

### Lookup returns wrong user/item

**Cause:** Multiple matches, first one returned.

**Fix:** Use more specific search terms or add filters.

---

## Related Documentation

- [Field Library Overview](../field-library/overview.md)
- [Form Designer](./designer.md)
- [Form Submission Processing](./submission.md)

---

*Next: [Form Designer](./designer.md)*

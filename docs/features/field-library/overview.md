# Shared Field Library — Overview

**Version:** 1.0+  
**Last Updated:** 2026-08-25

---

## What is the Field Library?

The **Shared Field Library** is a centralized repository of reusable field definitions that can be referenced by forms and CI types throughout the system.

Instead of defining the same field (e.g., "cost center", "employee ID", "department") multiple times across different forms with potentially different labels, types, or validation rules, you define it **once** in the library and reference it wherever needed.

### Benefits

1. **Consistency:** Same field definition everywhere — no drift
2. **Maintainability:** Update once, propagate to all references
3. **Discoverability:** Browse all available fields in one place
4. **Reuse:** Developers pick from existing fields instead of creating duplicates

---

## Core Concepts

### Field Definition

A **Field Definition** is a reusable template for a form or CI type field. It includes:

| Property | Description |
|----------|-------------|
| `key` | Unique identifier (slug), e.g., `cost_center`, `employee_id` |
| `label` | Human-readable name, e.g., "Cost Center" |
| `type` | Field type: `string`, `number`, `select`, `email`, etc. |
| `options` | For select fields: list of allowed values |
| `validation_rules` | Validation constraints (min_length, pattern, etc.) |
| `help_text` | Guidance shown to users |
| `owner` | User who created the field |
| `tags` | Organizational tags |
| `is_active` | Whether the field is available for use |
| `is_deprecated` | Whether the field is deprecated (still usable but discouraged) |

### Reference vs. Inline

Fields can be used in two ways:

1. **Inline:** Field definition embedded directly in form/CI type schema
   - Pros: Simple, self-contained
   - Cons: Duplicated definitions, hard to update globally

2. **Referenced (Library):** Field points to a `FieldDefinition` via `field_def_id`
   - Pros: Single source of truth, easy updates
   - Cons: Slightly more complex configuration

**Mixed mode is supported:** You can have some inline fields and some library references in the same form.

---

## Where Fields Are Used

### Forms
- Entry forms for workflows (portal submissions)
- Human task forms (approval/review steps)
- Custom data entry forms

### CI Types (CMDB)
- Field schemas for configuration items
- Define what data is collected for each CI type

### Report Definitions
- Column configurations
- Filter definitions

---

## Lifecycle

```
Create → Active → Deprecated → Archived
                ↑          ↓
                └──────────┘
           (reactivate if needed)
```

1. **Create:** Admin/developer creates field definition
2. **Active:** Available for use in forms/CI types
3. **Deprecated:** Still usable but shows warning; new references discouraged
4. **Archived:** Soft-deleted, cannot be referenced (hard delete available for admins)

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/field-library/` | List field definitions (paginated) |
| `GET` | `/field-library/{id}` | Get single field definition |
| `POST` | `/field-library/` | Create new field definition (admin) |
| `PUT` | `/field-library/{id}` | Update field definition (admin) |
| `POST` | `/field-library/{id}/deprecate` | Deprecate field (admin) |
| `DELETE` | `/field-library/{id}` | Hard delete (admin) |
| `GET` | `/field-library/{id}/where-used` | Show where field is referenced |

---

## UI Access

- **Admin:** `/admin/fields` — Full field manager
- **Data Dictionary:** `/admin/dictionary` — Browse all canonical fields
- **Form Designer:** When adding a field, click "📚 Add from Library" to pick existing definitions
- **CI Type Editor:** Same library picker for CI type field schemas

---

## Best Practices

1. **Use meaningful keys:** `cost_center` not `field_1`
2. **Add help text:** Explain what the field is for
3. **Tag appropriately:** Use tags for organization (e.g., `hr`, `finance`, `it`)
4. **Deprecate before deleting:** Allows time for references to update
5. **Review "where-used" before deprecating:** Understand impact

---

## Related Documentation

- [Creating Fields](./creating-fields.md)
- [Using in Forms](../forms/using-library-fields.md)
- [Using in CMDB](../cmdb/using-library-fields.md)
- [Migration Guide](./migration.md)

---

*Next: [Creating Fields](./creating-fields.md)*

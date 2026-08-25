# Form Designer

**Version:** 1.0+  
**Last Updated:** 2026-08-25

---

## Overview

The **Form Designer** is a visual builder for creating data entry forms used in:
- **Workflow entry forms** — User input before workflow execution
- **Human task forms** — Data collection during approval/review steps
- **Custom forms** — Standalone data collection

Forms are JSON Schema-based with a visual editor for ease of use.

### Access
- **Admin/Developer:** `/forms` → Click "Design" on any form
- **Portal Users:** Cannot access designer (use forms via workflows)

---

## Core Concepts

### Form
A collection of fields organized in a layout, with:
- **Name:** Unique identifier
- **Description:** Purpose of the form
- **Fields:** Input controls (text, number, select, lookup, etc.)
- **Layout:** Column configuration (1-4 columns)
- **Version:** Tracks changes
- **Status:** Draft, Published, Deactivated

### Fields
Individual input controls. Each field has:
- **Name:** Unique key (used in data)
- **Type:** Input control type
- **Title:** Label shown to users
- **Required:** Whether value is mandatory
- **Validation:** Rules (min/max length, pattern, etc.)
- **Options:** For select fields (dropdown choices)

---

## Creating a Form

### 1. Start New Form

```
Forms → + New Form
```

Enter:
- **Name:** (required, unique)
- **Description:** (optional)
- **Columns:** Layout width (1-4)

### 2. Add Fields

Click **+ Add Field** to add a new field to the form.

Choose field type from palette:
- **Text:** Single-line text input
- **Textarea:** Multi-line text
- **Number:** Numeric input
- **Email:** Email validation
- **Date/DateTime:** Date selection
- **Select:** Dropdown with options
- **Boolean:** Checkbox
- **File:** File upload
- **Lookup:** Search and select from users/CI items
- **Info:** Static text display (no input)

### 3. Configure Field

Click a field to open its configuration:

| Section | Description |
|---------|-------------|
| **Basic** | Name, title, type, required |
| **Validation** | Min/max length, pattern, custom rules |
| **Options** | For select fields: add/edit/remove choices |
| **Lookup** | For lookup fields: search config, auto-fill |
| **Library** | Reference shared field definitions |

### 4. Arrange Layout

- **Drag** fields to reorder
- **Resize** using column span controls
- **Group** related fields with info sections

### 5. Save and Publish

Click **Save Form** to save as draft.

Click **Publish** to make available for use:
- Attached to workflows as entry form
- Used in human task steps
- Accessible via portal

---

## Field Types Reference

### Text
Single-line text input.

**Configuration:**
```json
{
  "type": "string",
  "title": "Full Name",
  "required": true,
  "validation": {
    "minLength": 2,
    "maxLength": 100
  }
}
```

### Textarea
Multi-line text with row count.

**Configuration:**
```json
{
  "type": "textarea",
  "title": "Description",
  "rows": 4
}
```

### Number
Numeric input with optional constraints.

**Configuration:**
```json
{
  "type": "number",
  "title": "Amount",
  "required": true,
  "validation": {
    "min": 0,
    "max": 10000,
    "step": 0.01
  }
}
```

### Select
Dropdown with predefined options.

**Configuration:**
```json
{
  "type": "select",
  "title": "Priority",
  "options": ["Low", "Medium", "High"],
  "required": true
}
```

### Lookup
Search and select from users or CI items (see [Lookup Fields](./lookup-fields.md)).

**Configuration:**
```json
{
  "type": "lookup",
  "title": "Assignee",
  "lookup_config": {
    "target_type": "users",
    "search_field": "username",
    "display_field": "full_name",
    "result_fields": ["email"],
    "auto_fill": true
  }
}
```

### Boolean
Checkbox input.

**Configuration:**
```json
{
  "type": "boolean",
  "title": "Agree to terms"
}
```

### Date / DateTime
Date or date-time picker.

**Configuration:**
```json
{
  "type": "date",
  "title": "Start Date"
}
```

### File
File upload with size/type restrictions.

**Configuration:**
```json
{
  "type": "file",
  "title": "Attachment",
  "accept": ".pdf,.doc,.docx",
  "max_size_mb": 10
}
```

### Info
Static text display (no user input).

**Configuration:**
```json
{
  "type": "info",
  "content": "Please review the terms before submitting.",
  "text_align": "center"
}
```

---

## Using Library Fields

The **Shared Field Library** provides reusable field definitions. To use:

1. Click **📚 Add from Library** in field configuration
2. Search/browse available fields
3. Select a field definition
4. Configure any overrides (label, required, etc.)

**Benefits:**
- Consistent fields across forms
- Update once, propagate everywhere
- Reduced duplication

See [Field Library Overview](../field-library/overview.md) for details.

---

## Form Validation

Forms validate on submit:

1. **Required fields:** All marked required must have values
2. **Type checking:** Values match expected types
3. **Custom validation:** Pattern matching, min/max constraints
4. **Lookup validation:** Selected items exist and are active

**Error messages** display inline next to invalid fields.

---

## Submission Data

When a form is submitted, data is stored as JSON:

```json
{
  "field_name": "value",
  "lookup_field": 42,
  "auto_filled_email": "user@example.com"
}
```

Access in workflows via `$input.field_name`.

---

## Versioning

Forms track versions automatically:
- **Draft:** Unpublished, editable
- **Published:** Available for use, version incremented on changes
- **Deactivated:** Hidden from new use, existing runs unaffected

**Best practice:** Test changes in draft before publishing.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/forms` | List forms (paginated) |
| `GET` | `/forms/{id}` | Get form details |
| `POST` | `/forms` | Create form (admin/developer) |
| `PUT` | `/forms/{id}` | Update form (admin/developer) |
| `DELETE` | `/forms/{id}` | Delete form (admin) |
| `POST` | `/forms/{id}/publish` | Publish form |
| `POST` | `/forms/{id}/deactivate` | Deactivate form |
| `POST` | `/forms/{id}/submit` | Submit data to form |

---

## Best Practices

1. **Clear field names:** Use descriptive keys (`employee_id` not `field_1`)
2. **Group related fields:** Keep related inputs together visually
3. **Validate early:** Use required flags and constraints
4. **Test thoroughly:** Submit test data before publishing
5. **Document purpose:** Add descriptions explaining form usage
6. **Use library fields:** Avoid duplicating common fields
7. **Version carefully:** Test changes in draft first

---

## Related Documentation

- [Lookup Fields](./lookup-fields.md)
- [Field Library Overview](../field-library/overview.md)
- [Workflow Designer](../workflows/designer.md)
- [Human Tasks](../workflows/human-tasks.md)

---

*Next: [CMDB Overview](../cmdb/overview.md)*

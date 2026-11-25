# SQL Views

**Version:** 1.0+  
**Last Updated:** 2026-08-25

---

## Overview

**SQL VIEWs** are auto-generated read-only database views that provide a relational facade over JSONB data. They enable:

- **Structured querying** of form submissions and CI items
- **BI tool integration** (Tableau, Power BI, etc.)
- **Reporting** with standard SQL
- **Performance** via database-level indexing

### Naming Convention

- Form views: `v_form_<form_key>`
- CI type views: `v_ci_<ci_type_key>`

---

## How Views Are Generated

Views are generated from:
1. **Form schemas** — JSON Schema properties become columns
2. **CI type field schemas** — Field definitions become columns

**Example:** A form with fields `name`, `email`, `phone` generates:

```sql
CREATE VIEW v_form_contact_submission AS
SELECT 
    id,
    submitted_by,
    submitted_at,
    jsonb_extract_path_text(data, 'name') as name,
    jsonb_extract_path_text(data, 'email') as email,
    jsonb_extract_path_text(data, 'phone') as phone
FROM form_submissions
WHERE form_id = 42;
```

---

## Accessing Views

### Admin UI

1. Navigate to **Admin → SQL Views**
2. See list of generated views
3. Click **View** to see DDL
4. Click **Regenerate** to refresh (after form/CI type changes)

### Direct SQL Access

Views are accessible like any table:

```sql
SELECT * FROM v_form_contact_submission 
WHERE email LIKE '%@example.com';

SELECT name, COUNT(*) as submission_count 
FROM v_form_contact_submission 
GROUP BY name 
ORDER BY submission_count DESC;
```

---

## View Columns

### Form Submission Views

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Submission ID |
| `form_id` | INTEGER | Form that generated this view |
| `submitted_by` | INTEGER | User who submitted |
| `submitted_at` | TIMESTAMP | Submission timestamp |
| `[field_name]` | TEXT | Form field value (from JSONB) |

### CI Item Views

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | CI item ID |
| `type_id` | INTEGER | CI type |
| `name` | TEXT | Item name |
| `status` | TEXT | Item status |
| `[field_key]` | TEXT | CI field value (from JSONB) |

---

## Regenerating Views

Views should be regenerated when:
- Form schema changes (fields added/removed/renamed)
- CI type field schema changes
- Data types change

**Manual regeneration:**
1. Admin → SQL Views
2. Find view
3. Click **Regenerate**

**Automatic regeneration:**
- On form publish (if "auto-regenerate" enabled)
- On CI type save (if "auto-regenerate" enabled)

---

## View Permissions

Views inherit permissions from their source:
- **Form views:** Accessible to users who can view the form
- **CI views:** Accessible to CMDB managers

**Restrict access:** Modify view definition to filter by user/group.

---

## Performance Considerations

### Indexes

Views do not automatically index columns. Add indexes for frequently queried fields:

```sql
CREATE INDEX idx_v_form_contact_email ON v_form_contact_submission (email);
```

### Materialized Views

For large datasets, consider materialized views:

```sql
CREATE MATERIALIZED VIEW mv_form_contact_summary AS
SELECT submitted_by, COUNT(*) as submission_count
FROM v_form_contact_submission
GROUP BY submitted_by;

-- Refresh periodically
REFRESH MATERIALIZED VIEW mv_form_contact_summary;
```

### Query Optimization

Use views in WHERE clauses carefully:

```sql
-- Good: Filter on indexed columns
SELECT * FROM v_form_contact_submission 
WHERE submitted_at > '2026-01-01';

-- Avoid: Complex JSONB operations in WHERE
SELECT * FROM v_form_contact_submission 
WHERE data->>'name' LIKE '%john%';
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/admin/views` | List all generated views |
| `GET` | `/admin/views/{view_name}` | Get view DDL |
| `POST` | `/admin/views/regenerate/form/{form_id}` | Regenerate form view |
| `POST` | `/admin/views/regenerate/ci-type/{type_id}` | Regenerate CI view |
| `DELETE` | `/admin/views/{view_name}` | Drop a view |

---

## Troubleshooting

### View not found

**Cause:** View hasn't been generated yet.

**Fix:** Click **Regenerate** for the source form/CI type.

### Column missing from view

**Cause:** Field was removed from schema but view wasn't regenerated.

**Fix:** Regenerate the view.

### Permission denied

**Cause:** User doesn't have access to the underlying table.

**Fix:** Grant view access in user permissions.

---

## Related Documentation

- [Visual Query Builder](./visual-builder.md)
- [Reporting Overview](../reporting/overview.md)
- [Data Export](./export.md)

---

*Next: [Reporting Overview](../reporting/overview.md)*

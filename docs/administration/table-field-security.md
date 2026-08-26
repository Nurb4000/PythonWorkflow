# Table & Field-Level Security

**Version:** 1.0+  
**Last Updated:** 2026-08-25

---

## Overview

Table and field-level security provides granular control over which roles can:
- **View** specific tables
- **Edit** specific fields within tables
- **Delete** records from tables

This is the first phase of a comprehensive security model. Subsequent phases will integrate this with the query builder, form designer, and API middleware.

### Access Control Model

```
User → Roles → Role Permissions → Table/Field Access
                ↓
         Visible Fields (what user can see)
         Editable Fields (what user can modify)
```

---

## Configuration

### Admin UI

Navigate to **Admin → Role Permissions** (or use API directly).

**Endpoint:** `GET /admin/role-permissions/`

### Creating a Permission

**API:** `POST /admin/role-permissions/`

**Request body:**
```json
{
  "role_id": 5,
  "table_name": "configuration_items",
  "can_view": true,
  "can_edit": false,
  "can_delete": false,
  "visible_fields": ["name", "status", "type_id"],
  "editable_fields": [],
  "is_active": true
}
```

**Fields:**
- `role_id` — ID of the custom role
- `table_name` — Target table (e.g., `configuration_items`, `workflows`, `tasks`)
- `can_view` — Allow reading data from this table
- `can_edit` — Allow modifying data in this table
- `can_delete` — Allow deleting records
- `visible_fields` — List of field names user can see (or `["*"]` for all)
- `editable_fields` — List of field names user can modify (or `["*"]` for all)
- `is_active` — Enable/disable this permission

---

## Checking Access

### API Endpoints

**Check table access:**
```http
GET /admin/role-permissions/check/{table_name}?action=view
```

**Get visible fields:**
```http
GET /admin/role-permissions/visible-fields/{table_name}
```

**Get editable fields:**
```http
GET /admin/role-permissions/editable-fields/{table_name}
```

### Response Example

```json
{
  "access": true,
  "table": "configuration_items",
  "action": "view"
}
```

Or for field lists:
```json
{
  "table": "configuration_items",
  "fields": ["name", "status", "type_id"]
}
```

---

## Integration Points (Future Phases)

### Phase 1: Model + API ✅
- `RolePermission` model
- CRUD API for admins
- Access check endpoints

### Phase 2: Query Builder Integration ✅
- Filter results based on user's visible fields
- Prevent editing non-editable fields
- Example: Visual Query Builder only shows accessible tables/fields
- **Implemented:** `query_security_service.py` with `filter_query_results()` and `validate_query_access()`
- **Updated:** `/data-query/build` endpoint filters results by visible fields
- **Updated:** `/data-query/tables` endpoint filters table list by allowed tables

### Phase 3: Form Designer Integration ✅
- Hide non-visible fields in form editor
- Disable editing for non-editable fields
- Example: Form Designer only shows configurable fields
- **Implemented:** `/forms/{id}` endpoint filters schema properties by visible/editable fields
- **Implemented:** `/forms` endpoint checks access before listing forms
- **Added:** `_security` metadata to responses with `visible_fields` and `editable_fields` lists

### Phase 4: API Middleware 🔲
- Automatically filter responses by visible fields
- Reject writes to non-editable fields
- Example: `GET /cmdb/items` only returns accessible columns

### Phase 5: CMDB Integration 🔲
- Apply field-level security to CI data
- Restrict which CI fields are visible/editable per role
- Example: Support staff can view server name but not IP address

---

## Security Best Practices

1. **Default deny:** No permissions = no access
2. **Least privilege:** Grant minimum necessary access
3. **Audit regularly:** Review permissions quarterly
4. **Use groups:** Assign permissions to roles, not individual users
5. **Document access:** Maintain a permissions matrix
6. **Test thoroughly:** Verify access controls in staging first

---

## Troubleshooting

### User can't see table
**Check:**
- Role has `can_view: true` for the table
- Permission is active (`is_active: true`)
- User has the role assigned

### User sees wrong fields
**Check:**
- `visible_fields` list matches expected fields
- Field names match exactly (case-sensitive)
- No conflicting permissions from other roles

### Edit fails silently
**Check:**
- `can_edit: true` is set
- Field is in `editable_fields` list (or `"*"`)
- User has write permission on the table

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/admin/role-permissions/` | List all permissions |
| `POST` | `/admin/role-permissions/` | Create permission |
| `PUT` | `/admin/role-permissions/{id}` | Update permission |
| `DELETE` | `/admin/role-permissions/{id}` | Delete permission |
| `GET` | `/admin/role-permissions/check/{table}` | Check access |
| `GET` | `/admin/role-permissions/visible-fields/{table}` | Get visible fields |
| `GET` | `/admin/role-permissions/editable-fields/{table}` | Get editable fields |

---

## Related Documentation

- [Role Management](./role-management.md)
- [User Management](./user-management.md)
- [Security Overview](../security/overview.md)

---

*Next: Phase 2 — Query Builder Integration*

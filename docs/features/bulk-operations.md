# Bulk Operations

**Version:** 1.0+  
**Last Updated:** 2026-08-25

---

## Overview

Bulk operations allow administrators to perform actions on multiple items simultaneously:

- **Deprecate/Reactivate** workflows, forms, CI types
- **Reassign ownership** of content
- **Move items** between categories
- **Apply tags** in bulk

### Access
- **Admin:** `/admin/bulk` — Full bulk operation interface
- **Developer:** Limited to own content

---

## Available Operations

### Deprecate Items

Mark items as deprecated (hidden from new use, existing runs unaffected).

**Use cases:**
- Retiring old workflows
- Archiving unused forms
- Decommissioning CI types

**Steps:**
1. Admin → Bulk Operations → Select type (workflows/forms/CI types)
2. Filter to desired items
3. Select items (or "Select All")
4. Click **Deprecate Selected**
5. Confirm action

**Result:** Items marked `is_deprecated = true`, hidden from pickers.

### Reactivate Items

Restore previously deprecated items.

**Steps:**
1. Admin → Bulk Operations → Filter by "Deprecated" status
2. Select items
3. Click **Reactivate Selected**
4. Confirm

**Result:** Items marked `is_deprecated = false`, visible again.

### Reassign Ownership

Transfer ownership of items to another user.

**Use cases:**
- Employee departure
- Team restructuring
- Centralized management

**Steps:**
1. Admin → Bulk Operations → Select items
2. Click **Reassign Owner**
3. Choose new owner from dropdown
4. Confirm

**Result:** `owner_user_id` updated for all selected items.

### Apply Tags

Add tags to multiple items for organization.

**Steps:**
1. Admin → Bulk Operations → Select items
2. Click **Add Tags**
3. Enter tags (comma-separated)
4. Confirm

**Result:** Tags added to `tags` JSON array on each item.

### Remove Tags

Remove tags from multiple items.

**Steps:**
1. Admin → Bulk Operations → Select items
2. Click **Remove Tags**
3. Enter tags to remove
4. Confirm

**Result:** Tags removed from `tags` JSON array.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/bulk/workflows/deprecate` | Deprecate workflows |
| `POST` | `/bulk/workflows/reactivate` | Reactivate workflows |
| `POST` | `/bulk/workflows/reassign-owner` | Reassign workflow owners |
| `POST` | `/bulk/forms/deprecate` | Deprecate forms |
| `POST` | `/bulk/forms/reactivate` | Reactivate forms |
| `POST` | `/bulk/ci-types/deprecate` | Deactivate CI types |
| `POST` | `/bulk/ci-types/reactivate` | Reactivate CI types |

**Request body:**
```json
{
  "ids": [1, 2, 3],
  "new_owner_id": 42,
  "tags": ["archive", "2026"]
}
```

**Response:**
```json
{
  "success": true,
  "affected_count": 3,
  "ids": [1, 2, 3]
}
```

---

## Safety Features

### Confirmation Prompts

All bulk operations require explicit confirmation:

```
Are you sure you want to deprecate 15 workflows?

This will:
- Hide them from new workflow runners
- Keep existing runs unaffected
- Allow reactivation later

[Cancel] [Confirm Deprecation]
```

### Audit Logging

All bulk operations are logged:

- **Who** performed the operation
- **What** items were affected
- **When** it occurred
- **Why** (optional comment)

**View logs:** Admin → Audit Log → Filter by "bulk_operation"

### Rollback

Most operations can be reversed:

- Deprecated items → Reactivate
- Reassigned ownership → Reassign back
- Added tags → Remove tags

**Limitation:** Some operations (like permanent deletion) cannot be rolled back.

---

## Best Practices

1. **Test first:** Apply operations to a small subset before full rollout
2. **Document changes:** Add comments explaining why bulk operations were performed
3. **Monitor results:** Verify items updated correctly after operation
4. **Backup before major changes:** Export data before large-scale reassignments
5. **Use tags strategically:** Organize items with tags before bulk operations
6. **Review audit logs:** Regularly check bulk operation history

---

## Related Documentation

- [Deprecation Flow](../governance/deprecation.md)
- [Ownership Management](../administration/user-management.md)
- [Tagging System](../features/field-library/overview.md)

---

*Next: [Search API Reference](../api/search.md)*

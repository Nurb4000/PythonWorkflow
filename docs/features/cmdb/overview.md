# Configuration Management Database (CMDB)

**Version:** 1.0+  
**Last Updated:** 2026-08-25

---

## Overview

The **CMDB** is a centralized repository for tracking configuration items (CIs) — servers, applications, network devices, and other IT assets. It provides:

- **Structured data collection** via customizable CI types
- **Relationship tracking** between CIs
- **Dependency visualization** for impact analysis
- **Bulk operations** for efficient management
- **Audit logging** for compliance

### Access
- **Admin/Developer/CMDB Manager:** `/cmdb/types` and `/cmdb/items`
- **Portal Users:** Read-only access via lookups

---

## Core Concepts

### CI Type
A template defining the structure for a category of configuration items.

**Example:** "Server" CI type with fields: hostname, IP address, OS, location, owner.

### Configuration Item (CI)
An individual instance of a CI type.

**Example:** "web-prod-01" server with specific hostname, IP, etc.

### Relationships
Links between CIs showing dependencies.

**Example:** "web-prod-01" **depends_on** "database-01"

### Field Schema
Defines the structure for a CI type (similar to form fields).

---

## Creating a CI Type

### 1. Navigate to CI Types

```
CMDB → CI Types
```

### 2. Add New Type

Click **+ New CI Type**.

Enter:
- **Name:** Display name (e.g., "Server", "Application")
- **Key:** Unique identifier (e.g., `server`, `application`)
- **Description:** Purpose of this type
- **Icon:** Visual indicator (emoji or icon class)

### 3. Define Field Schema

Add fields to collect data for this CI type:

| Field Type | Use Case |
|------------|----------|
| **Text** | Hostname, name, description |
| **String** | IP address, MAC address |
| **Select** | Status (active/inactive), location |
| **Number** | CPU cores, memory (GB) |
| **Date** | Purchase date, warranty expiry |
| **Lookup** | Owner (user lookup), parent CI |

**Configuration per field:**
- Label (display name)
- Required/optional
- Validation rules
- Help text

### 4. Save and Activate

Click **Save**. Type is created in "active" state and ready for use.

---

## Creating Configuration Items

### 1. Navigate to CI Items

```
CMDB → CI Items
```

### 2. Select Type and Add Item

Choose a CI type from dropdown, then click **+ New Item**.

Fill in fields defined by the CI type's schema.

**Example — Server:**
- Hostname: `web-prod-01`
- IP Address: `10.0.1.50`
- OS: `Ubuntu 22.04` (from select options)
- Location: `DC1-Rack12`
- Owner: [Lookup field — search and select user]

### 3. Save

Item is created and appears in the list.

---

## Managing CIs

### Status Lifecycle

```
Active → Retired → Archived
   ↓
Deactivated (temporary)
```

- **Active:** In use, tracked
- **Retired:** No longer in service, data preserved
- **Archived:** Soft-deleted, recoverable
- **Deactivated:** Temporarily hidden from lists

### Bulk Operations

Select multiple items and:
- **Activate/Deactivate** — Toggle visibility
- **Change status** — Move through lifecycle
- **Assign owner** — Update ownership
- **Add tags** — Organize

### Search and Filter

- **By type:** Filter to specific CI categories
- **By status:** Active, retired, all
- **By text:** Search name, IP, etc.
- **By tag:** Filter by organizational tags

---

## Relationships

### Creating Relationships

1. Open a CI detail view
2. Click **Relationships** tab
3. Click **+ Add Relationship**
4. Select:
   - **Target CI:** The other item
   - **Type:** depends_on, connects_to, manages, etc.
   - **Properties:** Optional metadata

### Relationship Types

| Type | Description | Example |
|------|-------------|---------|
| `depends_on` | Requires the other to function | Web server depends on database |
| `connects_to` | Network or logical connection | Firewall connects to router |
| `manages` | Control relationship | NMS manages server |
| `monitors` | Monitoring relationship | APM monitors application |
| `contained_in` | Physical/logical containment | VM contained in host |
| `installed_on` | Software installation | App installed on server |

### Dependency Graph

Visualize relationships using the **Dependency Graph** viewer:

1. Open CI detail view
2. Click **Dependency Graph**
3. See nodes (CIs) and edges (relationships)
4. Expand/collapse to explore deeper

**Use cases:**
- Impact analysis: "What breaks if this server goes down?"
- Discovery: "What is this application connected to?"
- Documentation: Visual map of infrastructure

---

## Bulk Import/Export

### Import

Upload CSV or JSON files to create multiple CIs at once.

**Format:**
```csv
name,hostname,ip_address,os,status
web-prod-01,web01,10.0.1.50,Ubuntu 22.04,active
db-prod-01,db01,10.0.2.50,CentOS 8,active
```

**Steps:**
1. Navigate to CI Items → Select type
2. Click **Bulk Import**
3. Upload file or paste CSV/JSON
4. Map columns to CI type fields
5. Review and confirm

### Export

Download CIs as CSV or JSON for reporting or migration.

**Steps:**
1. Filter to desired items
2. Click **Export**
3. Choose format (CSV/JSON)
4. Download file

---

## Audit Trail

All CI changes are logged:

- **Who** made the change
- **What** changed (field, old value, new value)
- **When** it happened
- **Why** (optional comment)

View history:
1. Open CI detail view
2. Click **History** tab
3. See chronological list of changes

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/cmdb/types` | List CI types |
| `POST` | `/cmdb/types` | Create CI type (admin) |
| `PUT` | `/cmdb/types/{id}` | Update CI type (admin) |
| `DELETE` | `/cmdb/types/{id}` | Deactivate CI type (admin) |
| `GET` | `/cmdb/items` | List CIs (paginated) |
| `POST` | `/cmdb/items` | Create CI |
| `PUT` | `/cmdb/items/{id}` | Update CI |
| `DELETE` | `/cmdb/items/{id}` | Deactivate CI |
| `GET` | `/cmdb/items/{id}/relationships` | Get relationships |
| `POST` | `/cmdb/relationships` | Create relationship |
| `DELETE` | `/cmdb/relationships/{id}` | Delete relationship |
| `GET` | `/cmdb/items/{id}/graph` | Get dependency graph |
| `POST` | `/cmdb/items/bulk-import` | Bulk import CIs |
| `GET` | `/cmdb/items/export` | Export CIs |

---

## Best Practices

1. **Consistent naming:** Use clear, unique names for CIs
2. **Regular audits:** Review and clean up retired items quarterly
3. **Tag strategically:** Use tags for organization (env, team, location)
4. **Document relationships:** Add properties to explain why CIs are linked
5. **Backup before bulk ops:** Export before mass updates
6. **Use lookups:** Reference users/other CIs instead of free text
7. **Monitor changes:** Review audit logs for unauthorized modifications

---

## Related Documentation

- [CI Types Guide](./ci-types.md)
- [CI Items Management](./items.md)
- [Relationships Deep Dive](./relationships.md)
- [Bulk Import/Export](./bulk-import.md)
- [Field Library](../field-library/overview.md)

---

*Next: [CI Types Guide](./ci-types.md)*

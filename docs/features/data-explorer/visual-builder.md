# Visual Query Builder

**Version:** 1.0+  
**Last Updated:** 2026-08-25

---

## Overview

The **Visual Query Builder** allows users to construct SQL queries without writing SQL. It provides a graphical interface for:

- Selecting tables and columns
- Adding filters (WHERE conditions)
- Choosing aggregation functions (SUM, COUNT, AVG, etc.)
- Sorting results
- Limiting output

### Access
- **Admin/Developer:** `/data-explorer` → Visual Builder tab
- **Portal Users:** Read-only access via saved queries

---

## Building a Query

### 1. Select Table

Choose a table from the dropdown:
- `configuration_items` — CI items
- `workflows` — Workflow definitions
- `tasks` — Task records
- Custom tables (if any)

### 2. Choose Columns

Select columns to include in results:
- Checkboxes for each column
- Drag to reorder
- Rename aliases (optional)

### 3. Add Filters

Click **+ Add Filter** to create WHERE conditions:

| Field | Operator | Value |
|-------|----------|-------|
| Column selector | `=`, `!=`, `>`, `<`, `>=`, `<=`, `LIKE`, `IN` | Value or expression |

**Example:**
```
status = 'active'
name LIKE '%server%'
type_id IN (1, 2, 3)
```

### 4. Add Aggregations

For summary queries, add aggregation functions:

| Function | Description | Example |
|----------|-------------|---------|
| `COUNT(*)` | Row count | Total items |
| `SUM(column)` | Sum of values | Total revenue |
| `AVG(column)` | Average value | Average response time |
| `MIN(column)` | Minimum value | Earliest date |
| `MAX(column)` | Maximum value | Latest date |

**Group by:** Specify column(s) to group aggregations by.

### 5. Sort Results

Add sort criteria:
- Column selector
- Direction: Ascending / Descending

### 6. Limit Results

Set maximum rows to return (default: 100, max: 10000).

### 7. Execute Query

Click **Run Query** to see results in a table.

---

## Query Examples

### Example 1: List All Active Servers

```
Table: configuration_items
Columns: name, ip_address, os, status
Filter: status = 'active' AND type_id = 1 (Server)
Sort: name ASC
Limit: 100
```

**Generated SQL:**
```sql
SELECT name, ip_address, os, status 
FROM configuration_items 
WHERE status = 'active' AND type_id = 1 
ORDER BY name ASC 
LIMIT 100;
```

### Example 2: Count Items by Type

```
Table: configuration_items
Aggregation: COUNT(*) as item_count
Group by: type_id
Sort: item_count DESC
```

**Generated SQL:**
```sql
SELECT type_id, COUNT(*) as item_count 
FROM configuration_items 
GROUP BY type_id 
ORDER BY item_count DESC;
```

### Example 3: Find High-Priority Tasks

```
Table: tasks
Columns: title, status, assigned_to_user_id, priority
Filter: priority <= 2 AND status IN ('open', 'owned')
Sort: priority ASC, created_at DESC
Limit: 50
```

**Generated SQL:**
```sql
SELECT title, status, assigned_to_user_id, priority 
FROM tasks 
WHERE priority <= 2 AND status IN ('open', 'owned') 
ORDER BY priority ASC, created_at DESC 
LIMIT 50;
```

---

## Saved Queries

Save frequently used queries for reuse:

1. Build query using visual builder
2. Click **Save Query**
3. Enter name and optional description
4. Query is stored in `saved_queries` table

**Access saved queries:**
- `/data-explorer` → Saved Queries tab
- Execute with one click
- Edit to modify

---

## Export Results

After running a query, export results:

| Format | Use Case |
|--------|----------|
| **CSV** | Spreadsheet analysis, reporting |
| **JSON** | API integration, programmatic access |
| **Excel** | Formatted reports with charts |

**Steps:**
1. Run query
2. Click **Export** button
3. Choose format
4. Download file

---

## Query Builder API

For programmatic access, use the API:

### Execute Query

```http
POST /api/data-query/execute
Content-Type: application/json

{
  "table": "configuration_items",
  "columns": ["name", "ip_address", "status"],
  "filters": [
    {"column": "status", "operator": "=", "value": "active"}
  ],
  "sort": [{"column": "name", "direction": "asc"}],
  "limit": 100
}
```

**Response:**
```json
{
  "results": [
    {"name": "web-prod-01", "ip_address": "10.0.1.50", "status": "active"},
    {"name": "db-prod-01", "ip_address": "10.0.2.50", "status": "active"}
  ],
  "total": 42,
  "sql": "SELECT name, ip_address, status FROM configuration_items WHERE status = 'active' ORDER BY name ASC LIMIT 100"
}
```

### List Saved Queries

```http
GET /api/data-query/saved
```

### Execute Saved Query

```http
POST /api/data-query/execute-saved/{query_id}
```

---

## Security Considerations

### Read-Only Access

The visual query builder is **read-only** by design:
- No INSERT, UPDATE, DELETE operations
- No DDL (CREATE, ALTER, DROP)
- No stored procedures

### Table Restrictions

Admins can restrict which tables are accessible:
- **Default:** All application tables
- **Custom:** Selective access based on user role

### Query Timeouts

Long-running queries are terminated after 30 seconds (configurable).

### Result Limits

Maximum 10,000 rows per query to prevent memory issues.

---

## Troubleshooting

### Query Returns No Results

**Check:**
- Filters are correct
- Table has data
- Column names match exactly

### Query Takes Too Long

**Solutions:**
- Add more specific filters
- Reduce result limit
- Check for missing indexes
- Contact admin to optimize

### Permission Denied

**Cause:** User doesn't have access to the table.

**Fix:** Admin grants table access in user permissions.

---

## Related Documentation

- [SQL Views](./sql-views.md)
- [Reporting](../reporting/overview.md)
- [Data Export](./export.md)

---

*Next: [SQL Views](./sql-views.md)*

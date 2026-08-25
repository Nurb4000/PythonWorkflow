# Report Definition Knowledge Base

## Purpose
Generate report definitions from natural language descriptions.

## Report Types

### SQL VIEW Reports
Based on auto-generated SQL VIEWs for forms and CI types.

**Structure:**
```json
{
  "name": "Weekly Server Inventory",
  "description": "List all active servers with details",
  "source": "sql_view",
  "view_name": "v_ci_server",
  "columns": [
    {"field": "name", "label": "Server Name"},
    {"field": "ip_address", "label": "IP Address"},
    {"field": "os", "label": "Operating System"}
  ],
  "filters": [
    {"column": "status", "operator": "=", "value": "active"}
  ],
  "sort": [{"column": "name", "direction": "asc"}],
  "limit": 100
}
```

### Custom Query Reports
Built using the Visual Query Builder.

**Structure:**
```json
{
  "name": "Monthly Submission Count",
  "description": "Count form submissions by month",
  "source": "custom_query",
  "table": "form_submissions",
  "columns": [
    {"field": "extract(month from submitted_at)", "label": "Month"},
    {"field": "count(*)", "label": "Submission Count", "aggregate": true}
  ],
  "group_by": ["extract(month from submitted_at)"],
  "filters": [
    {"column": "submitted_at", "operator": ">=", "value": "2026-01-01"}
  ],
  "sort": [{"column": "Month", "direction": "desc"}]
}
```

### Form Submission Reports
Aggregate data from form submissions.

**Structure:**
```json
{
  "name": "Request Summary by Type",
  "description": "Count requests grouped by type",
  "source": "form_submission",
  "form_id": 42,
  "columns": [
    {"field": "request_type", "label": "Request Type"},
    {"field": "count(*)", "label": "Count", "aggregate": true}
  ],
  "group_by": ["request_type"],
  "sort": [{"column": "Count", "direction": "desc"}]
}
```

## Best Practices

1. **Clear naming:** Use descriptive names like "Weekly Server Inventory" not "Report 1"
2. **Add descriptions:** Explain purpose and audience
3. **Limit results:** Set reasonable limits (default 100, max 10000)
4. **Use filters:** Narrow down data to relevant subset
5. **Sort logically:** Most useful data first
6. **Test before scheduling:** Run manually to verify output

## Common Patterns

### Time-based Aggregations
```json
{
  "columns": [
    {"field": "extract(month from submitted_at)", "label": "Month"},
    {"field": "count(*)", "label": "Count", "aggregate": true}
  ],
  "group_by": ["extract(month from submitted_at)"],
  "filters": [
    {"column": "submitted_at", "operator": ">=", "value": "2026-01-01"}
  ]
}
```

### Status Summaries
```json
{
  "columns": [
    {"field": "status", "label": "Status"},
    {"field": "count(*)", "label": "Count", "aggregate": true}
  ],
  "group_by": ["status"]
}
```

### Top N Results
```json
{
  "columns": [
    {"field": "name", "label": "Server Name"},
    {"field": "ip_address", "label": "IP Address"}
  ],
  "sort": [{"column": "name", "direction": "asc"}],
  "limit": 10
}
```

## Output Format

Reports can be exported as:
- **CSV** — Spreadsheet analysis
- **JSON** — API integration
- **Excel** — Formatted reports with charts

## Scheduled Delivery

Reports can be scheduled via cron expression:
- `0 9 * * *` — Daily at 9 AM
- `0 9 * * 1` — Mondays at 9 AM
- `*/30 * * * *` — Every 30 minutes

Recipients receive email with report attached.

# Report Node Knowledge Base

## Context
Report nodes (`report`) render data as tables, graphs, or read-only forms. They can execute SQL queries to fetch data for display.

## Report Types
- `table` - Tabular data display
- `graph` - Chart visualization
- `readonly_form` - Formatted single-record display
- `sql_query` - Custom SQL with result table

## Generation Patterns

### SQL Query Report
```json
{
  "report_type": "sql_query",
  "title": "Monthly Sales Summary",
  "sql_query": "SELECT DATE_TRUNC('month', created_at) as month, SUM(amount) as total FROM orders WHERE created_at >= NOW() - INTERVAL '3 months' GROUP BY month ORDER BY month DESC",
  "sql_limit": 100
}
```

### Table Report
```json
{
  "report_type": "table",
  "title": "Pending Tasks",
  "sql_query": "SELECT id, title, assigned_to_id, created_at FROM tasks WHERE status = 'open' ORDER BY created_at DESC",
  "sql_limit": 50
}
```

## Explanation Patterns
- Describe the report type, title, and what data it displays.
- Explain the SQL query in plain English.
- Note the row limit.

## Fix Patterns
- Common errors: invalid SQL syntax, column not found, missing GROUP BY.
- Suggest adding WHERE clauses for data filtering.
- Remind that only SELECT queries are allowed.

## Safety Rules
- Only SELECT queries are permitted.
- Dangerous keywords blocked: DROP, DELETE, UPDATE, INSERT, ALTER, CREATE, TRUNCATE.
- 30-second query timeout, 10,000 row limit.
- `$input.field` interpolation supported for dynamic queries.

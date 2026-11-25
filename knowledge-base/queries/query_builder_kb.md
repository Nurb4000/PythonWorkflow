# Query Builder Knowledge Base

## Context
The query builder allows users to construct data queries visually or via SQL. It operates on the platform's database tables with support for native columns, custom fields, and relationship joins.

## Available Tables & Key Columns

### tasks
- `id`, `title`, `description`, `status` (open/assigned/in_progress/completed/rejected/closed), `assigned_to_id`, `created_at`, `completed_at`

### workflow_runs
- `id`, `workflow_id`, `status` (running/completed/failed/cancelled/paused), `started_at`, `finished_at`, `triggered_by`

### step_instances
- `id`, `run_id`, `step_id`, `step_type`, `status`, `input_data`, `output_data`, `error_message`, `started_at`, `finished_at`

### users
- `id`, `username`, `email`, `full_name`, `role` (admin/developer/staff/user), `is_active`, `created_at`

### form_submissions
- `id`, `form_id`, `workflow_run_id`, `data`, `submitted_at`

## Visual Builder Patterns

### Filter Construction
```json
{
  "table": "tasks",
  "filters": [
    {"field": "status", "operator": "=", "value": "open"},
    {"field": "assigned_to_id", "operator": "=", "value": "$input.user_id"}
  ],
  "logic": "AND"
}
```

### Available Operators
- `=`, `!=`, `>`, `<`, `>=`, `<=`
- `contains`, `starts_with`, `ends_with`
- `is_null`, `in` (comma-separated values)

## SQL Generation Patterns

### Natural Language to SQL
- "Show me all open tasks" -> `SELECT * FROM tasks WHERE status = 'open'`
- "Failed workflow runs this week" -> `SELECT * FROM workflow_runs WHERE status = 'failed' AND started_at >= NOW() - INTERVAL '7 days'`
- "Tasks assigned to user 5 that are overdue" -> `SELECT * FROM tasks WHERE assigned_to_id = 5 AND status != 'completed'`

## Explanation Patterns
- Describe what tables are queried, what filters apply, and expected result count.
- For SQL: break down the query into its components (SELECT columns, FROM table, WHERE conditions, ORDER BY, LIMIT).

## Fix Patterns
- Common errors: column not found, invalid operator, syntax error in SQL.
- Suggest checking table/column names against available schema.
- For SQL: suggest adding LIMIT, fixing quoting, correcting JOIN syntax.

## Safety Rules
- Only SELECT queries allowed in SQL editor.
- Dangerous keywords blocked: DROP, DELETE, UPDATE, INSERT, ALTER, CREATE, TRUNCATE.
- 30-second timeout, 10,000 row limit.

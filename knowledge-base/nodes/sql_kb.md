# SQL Node Knowledge Base

## Context
SQL nodes (`database_query`) execute parameterized queries against the workflow's PostgreSQL database. They support SELECT, INSERT, UPDATE, DELETE, and UPSERT operations.

## Available Tables
- `tasks` - Workflow human tasks and approvals
- `workflow_runs` - Execution history of workflows
- `step_instances` - Individual step execution records
- `users` - Platform users
- `groups` - User groups/roles
- `form_submissions` - Collected form data
- `workflows` - Workflow definitions
- `workflow_steps` - Step configurations
- `forms` - Form definitions
- `schedules` - Cron-based workflow triggers

## Generation Patterns

### SELECT Query
```json
{
  "type": "select",
  "table": "tasks",
  "query": "SELECT * FROM tasks WHERE status = 'open' AND assigned_to_id = $input.user_id LIMIT 50"
}
```

### INSERT Query
```json
{
  "type": "insert",
  "table": "form_submissions",
  "query": "INSERT INTO form_submissions (workflow_run_id, data) VALUES ($input.run_id, $input.form_data)"
}
```

### UPDATE Query
```json
{
  "type": "update",
  "table": "tasks",
  "query": "UPDATE tasks SET status = 'completed', completed_at = NOW() WHERE id = $input.task_id"
}
```

## Explanation Patterns
- Describe what tables are queried, what filters apply, and what data is returned.
- Note any `$input.*` variable references and their upstream sources.

## Fix Patterns
- Common errors: column not found, table not found, syntax errors, missing WHERE clause.
- Always suggest parameterized values using `$input.field` rather than hardcoded values.
- For SELECT queries, suggest adding LIMIT if none present.

## Safety Rules
- SELECT-only for report nodes and data explorer.
- Database query nodes may use INSERT/UPDATE/DELETE but must always have a WHERE clause for mutations.
- Never generate queries that reference system tables (pg_catalog, information_schema) unless explicitly requested.
- Table and column names are validated against the actual schema at runtime.

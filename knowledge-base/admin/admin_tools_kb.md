# Admin Tools Knowledge Base

## Context
Admin tools provide platform management capabilities: user management, schedule configuration, data exploration, SQL view management, and workflow monitoring.

## Schedule Patterns

### Cron Expression Reference
- `*/5 * * * *` - Every 5 minutes
- `0 */2 * * *` - Every 2 hours
- `0 9 * * *` - Daily at 9 AM
- `0 9 * * 1-5` - Weekdays at 9 AM
- `0 0 * * 0` - Sundays at midnight
- `0 0 1 * *` - First of each month at midnight
- `0 */6 * * *` - Every 6 hours

### Schedule Configuration
```json
{
  "workflow_id": 5,
  "cron_expression": "0 9 * * 1-5",
  "is_active": true,
  "input_data": {"environment": "production"}
}
```

## User Management Patterns

### Role Assignment
- `admin` - Full platform access
- `developer` - Workflow design and development
- `staff` - Task execution and monitoring
- `user` - Portal access only

### Common Queries
- "List inactive users": `SELECT * FROM users WHERE is_active = false`
- "Users by role": `SELECT role, COUNT(*) FROM users GROUP BY role`
- "Recent registrations": `SELECT * FROM users ORDER BY created_at DESC LIMIT 20`

## Workflow Monitoring Patterns

### Run Statistics
- Total runs, completed, failed, average duration
- Filter by workflow, date range, status
- Search by workflow name or triggered_by user

### Audit Trail
- Step-by-step execution log
- Input/output data for each step
- Error messages and timestamps

## SQL View Patterns

### Creating Views
```sql
CREATE VIEW active_tasks AS
SELECT t.id, t.title, t.status, u.full_name as assignee
FROM tasks t
LEFT JOIN users u ON t.assigned_to_id = u.id
WHERE t.status IN ('open', 'assigned', 'in_progress');
```

### Safety Rules
- Only CREATE VIEW is allowed (no DROP, ALTER on base tables).
- Views are synced on application startup.
- Dangerous keywords blocked in view definitions.

# Workflow Designer

**Version:** 1.0+  
**Last Updated:** 2026-08-25

---

## Overview

The **Workflow Designer** is a visual, drag-and-drop interface for creating and editing workflows. Workflows are sequences of steps that execute automatically or with human intervention.

### Access
- **Admin/Developer:** `/workflows` → Click "Design" on any workflow
- **Portal Users:** Cannot access designer (read-only run monitoring)

---

## Core Concepts

### Workflow
A configurable sequence of steps with:
- **Name:** Unique identifier (case-insensitive)
- **Description:** What the workflow does
- **Steps:** Ordered list of execution nodes
- **Entry Form:** Optional form for user input before execution
- **Tags:** Organizational metadata
- **Owner:** Responsible user

### Steps
Individual execution nodes. Each step has:
- **Type:** `api_call`, `database_query`, `email`, `condition`, `human_task`, etc.
- **Configuration:** Type-specific settings
- **Connections:** Links to next step(s) based on outcome

---

## Creating a Workflow

### 1. Start New Workflow

```
Workflows → + New Workflow
```

Enter:
- **Name:** (required, unique)
- **Description:** (optional)
- **Tags:** (optional, comma-separated)

### 2. Add Steps

Click **+ Add Step** in the designer canvas.

Choose step type from palette:
- **Start:** Entry point (always first)
- **End:** Exit point (always last)
- **API Call:** HTTP requests
- **Database Query:** SQL operations
- **Email:** Send notifications
- **Condition:** Branching logic
- **Delay:** Wait before continuing
- **Human Task:** Assign to user/group
- **Custom Code:** Python execution
- And more...

### 3. Configure Step

Click a step to open its configuration panel:

| Section | Description |
|---------|-------------|
| **Title** | Display name for the step |
| **Definition** | Type-specific configuration |
| **Conditions** | When this step executes |
| **Error Handling** | Retry, timeout, failure hooks |

### 4. Connect Steps

Drag from output port (right) of one step to input port (left) of next.

**Condition steps** have multiple outputs (route A, route B, default).

### 5. Save

Click **Save Workflow**. Validates:
- All steps connected
- No circular dependencies
- Required fields populated
- Naming rules (unique, <80 chars)

---

## Step Types Reference

### API Call
Make HTTP requests to external services.

**Configuration:**
```json
{
  "method": "GET|POST|PUT|DELETE",
  "url": "https://api.example.com/data",
  "headers": {"Authorization": "Bearer ..."},
  "body": "{\"key\": \"value\"}",
  "timeout": 30
}
```

**Input/Output:**
- **Input:** `$input.field_name` from entry form or upstream steps
- **Output:** Response body in `result_data`

---

### Database Query
Execute SQL queries against the application database.

**Configuration:**
```json
{
  "query_type": "SELECT|INSERT|UPDATE|DELETE",
  "sql": "SELECT * FROM users WHERE active = true",
  "parameters": {"$input.user_id": "id"}
}
```

⚠️ **Security:** Only parameterized queries allowed. No raw SQL injection.

---

### Email
Send email notifications via configured SMTP.

**Configuration:**
```json
{
  "to": "$input.recipient_email",
  "subject": "Workflow Notification",
  "body": "Hello $input.name,",
  "html": true
}
```

Uses `$input.*` interpolation for dynamic content.

---

### Condition
Branch workflow based on expressions.

**Configuration:**
```json
{
  "routes": [
    {"expression": "data['amount'] > 1000", "target_step_id": 3},
    {"expression": "data['priority'] == 'high'", "target_step_id": 4}
  ],
  "default_target_step_id": 5
}
```

Expressions use Python syntax over `data` dictionary.

---

### Human Task
Pause workflow for user action.

**Configuration:**
```json
{
  "title": "Approve Request",
  "description": "Review and approve or reject",
  "assigned_to_user_id": "$input.manager_id",
  "form_id": 12,
  "timeout_hours": 48
}
```

Task appears in:
- **Admin:** `/admin/tasks`
- **Staff/User:** `/tasks` or `/my-tasks`

---

## Data Flow

### Input Data (`$input.*`)

Available in steps:
1. **Entry form fields** — if workflow has an entry form
2. **Upstream step results** — merged in order
3. **System variables** — `workflow_id`, `run_id`, etc.

### Output Data (`result_data`)

Each step can return data:
- **API Call:** Response body
- **Database Query:** Rows affected, returned data
- **Email:** Send status
- **Human Task:** Form submission data

Data flows downstream via `$input.field_name`.

---

## Execution Modes

### Manual
Triggered by user from workflow detail page.

### Scheduled
Executed automatically via cron-like scheduler.

**Configuration:**
```json
{
  "cron": "0 9 * * *",  // Daily at 9 AM
  "timezone": "UTC"
}
```

### Webhook
Triggered by external HTTP POST.

**Endpoint:** `POST /webhook/{workflow_id}?secret=...`

### Sub-Workflow
Called synchronously from another workflow (Phase B3).

**Step Type:** `sub_workflow`

**Configuration:**
```json
{
  "workflow_id": 42,
  "input_data": {"$input.user_id": "user_id"},
  "timeout_seconds": 300
}
```

Waits for completion, returns result_data.

---

## Debugging

### Run Inspector
View execution details for a run:

1. Open workflow → **Runs** tab
2. Click run ID → **Inspector**
3. See:
   - Step-by-step execution
   - Input/output data per step
   - Timing information
   - Error messages

### Test Mode
Run workflow with sample data before publishing.

**Form Designer:** Click "Test Run" button.

### Logs
Check backend logs for errors:
```bash
docker compose logs -f backend
```

Or view in Admin Dashboard → System Logs.

---

## Best Practices

1. **Name clearly:** `employee_onboarding`, not `workflow_1`
2. **Add descriptions:** Explain purpose and usage
3. **Use tags:** Organize by department, purpose, etc.
4. **Test before publish:** Use test mode with sample data
5. **Handle errors:** Add error steps for failed API calls, etc.
6. **Document complex logic:** Add comments in step descriptions
7. **Version control:** Use manual version increments for major changes

---

## Related Documentation

- [Step Types Reference](./steps.md)
- [Conditions and Routing](./conditions.md)
- [Human Tasks](./human-tasks.md)
- [Field Library](../field-library/overview.md)
- [Lookup Fields](../forms/lookup-fields.md)

---

*Next: [Step Types Reference](./steps.md)*

# Human Tasks

**Version:** 1.0+  
**Last Updated:** 2026-08-25

---

## Overview

**Human tasks** pause workflow execution until a user completes an action (approve, reject, provide data, etc.). They enable **human-in-the-loop** automation for:

- Approval workflows (expense requests, change management)
- Data collection (intake forms, surveys)
- Review processes (code review, content moderation)
- Exception handling (error recovery, manual intervention)

### Task Lifecycle

```
Open → Owned → Completed → Closed
  ↓        ↓
Review   (optional)
```

---

## Creating a Human Task Step

In the Workflow Designer, add a **Human Task** step:

**Configuration:**
```json
{
  "step_type": "human_task",
  "title": "Manager Approval",
  "description": "Approve or reject the request",
  "assigned_to_user_id": "$input.manager_id",
  "form_id": 12,
  "timeout_hours": 48,
  "priority": 1
}
```

**Fields:**
- **Title:** Display name for the task
- **Description:** Instructions for the assignee
- **Assigned To:** User ID or expression (e.g., `$input.manager_id`)
- **Form ID:** Optional form for data collection
- **Timeout:** Hours before escalation (optional)
- **Priority:** Task priority (1=highest, 5=lowest)

---

## Task Assignment

### Direct Assignment
Assign to a specific user:
```json
"assigned_to_user_id": 42
```

### Dynamic Assignment
Use workflow data or expressions:
```json
"assigned_to_user_id": "$input.manager_id"
```

### Group Assignment
Assign to a group (any member can take the task):
```json
"assigned_group_id": 5
```

### Self-Service
Leave unassigned — users claim tasks from their queue.

---

## Task Views

### Admin Tasks (`/admin/tasks`)
- View all tasks across the system
- Filter by status, assignee, workflow
- Reassign or close tasks
- View task history

### My Tasks (`/tasks` or `/my-tasks`)
- **Staff/User:** Tasks assigned to me or my group
- **Developer/Admin:** All tasks + own tasks

### Task Detail (`/tasks/{id}`)
- Full task information
- Associated form (if any)
- History and audit log
- Actions: Take, Complete, Reject, Close

---

## Task Actions

### Open → Owned
User "takes" the task, marking it as in progress.

**API:** `POST /tasks/{id}/take`

### Owned → Completed
User finishes the work and submits results.

**With form:** Fill out associated form and submit.  
**Without form:** Click "Complete" and optionally add comments.

**API:** `POST /tasks/{id}/complete` with `result_data`

### Owned → Review
Task sent back for review (optional step).

**API:** `POST /tasks/{id}/review`

### Review → Completed
Reviewer approves the task.

**API:** `POST /tasks/{id}/complete`

### Completed → Closed
Finalize the task (admin/developer only).

**API:** `POST /tasks/{id}/close`

### Rejection
Reject the task with reason (returns to previous step or cancels).

**API:** `POST /tasks/{id}/reject` with `reason`

---

## SLA/OLA Pause States

Tasks can be paused to halt SLA/OLA timers:

| State | Description | SLA Impact |
|-------|-------------|------------|
| `in_process` | Active, working on task | Timer running |
| `pending_customer_feedback` | Waiting on customer | **Paused** |
| `scheduled_with_customer` | Appointment set | **Paused** |
| `pending_vendor` | Waiting on vendor | **Paused** |
| `pending_internal_team` | Waiting on internal team | **Paused** |
| `scheduled` | Future scheduled work | **Paused** |

**Set pause state:** Task detail → dropdown → select state → "Set Pause"

**Resume:** Click "Resume" to return to `in_process`.

---

## Escalation

If a task times out:

1. **Notification sent** to admin (configurable)
2. **Task status** remains unchanged (manual escalation required)
3. **Workflow continues** only after task completion

**Custom escalation:** Add a parallel branch in the workflow that triggers on timeout.

---

## Task Data

### Input Data (`task_data`)
Data passed to the task from upstream steps or entry form.

**Example:**
```json
{
  "request_id": "REQ-001",
  "amount": 5000,
  "requester_email": "john@example.com"
}
```

### Result Data (`result_data`)
Data submitted by the user upon completion.

**Example (with form):**
```json
{
  "approved": true,
  "comments": "Looks good, proceed",
  "risk_level": "low"
}
```

**Access in downstream steps:** `$input.result_data.approved`

---

## Notifications

Tasks trigger notifications:

- **Assignment:** When task is assigned to a user/group
- **Update:** When task status changes
- **Completion:** When task is completed
- **Timeout:** When task approaches deadline

**Configure:** Admin → Settings → Email (SMTP setup required)

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/tasks` | List tasks (paginated, filterable) |
| `GET` | `/tasks/{id}` | Get task details |
| `POST` | `/tasks/{id}/open` | Reopen a closed task |
| `POST` | `/tasks/{id}/take` | Take ownership of task |
| `POST` | `/tasks/{id}/review` | Send to review |
| `POST` | `/tasks/{id}/complete` | Complete task |
| `POST` | `/tasks/{id}/close` | Close task |
| `POST` | `/tasks/{id}/reject` | Reject task with reason |
| `PUT` | `/tasks/{id}` | Update task (admin) |
| `DELETE` | `/tasks/{id}` | Delete task (admin) |
| `POST` | `/portal/my-tasks` | Get my tasks (portal users) |

---

## Best Practices

1. **Clear titles:** Describe what the user needs to do
2. **Detailed descriptions:** Include context and instructions
3. **Set priorities:** Use priority field for urgency
4. **Add forms:** Collect structured data instead of free text
5. **Configure timeouts:** Prevent tasks from being forgotten
6. **Use pause states:** Track why a task is stalled
7. **Review regularly:** Admin should audit open tasks weekly

---

## Related Documentation

- [Workflow Designer](./designer.md)
- [Form Designer](../forms/designer.md)
- [SLA/OLA Pause States](../../administration/sla-ola.md)
- [Notifications](../../administration/email-setup.md)

---

*Next: [Conditions and Routing](./conditions.md)*

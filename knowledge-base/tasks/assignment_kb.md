# Task Assignment Knowledge Base

## Purpose
Assist with task assignment, priority calculation, and escalation rules.

## Task Assignment Patterns

### Direct Assignment
Assign to a specific user:
```json
{
  "assigned_to_user_id": 42,
  "assignment_type": "direct"
}
```

### Group Assignment
Assign to a group (any member can take):
```json
{
  "assigned_group_id": 5,
  "assignment_type": "group"
}
```

### Dynamic Assignment
Use workflow data to determine assignee:
```json
{
  "assigned_to_user_id": "$input.manager_id",
  "assignment_type": "dynamic"
}
```

### Round-Robin
Distribute tasks evenly among group members:
```json
{
  "assigned_group_id": 5,
  "assignment_type": "round_robin"
}
```

## Priority Levels

| Priority | Level | Description | Response Time |
|----------|-------|-------------|---------------|
| P1 | Critical | System down, data loss | 15 minutes |
| P2 | High | Major feature broken | 1 hour |
| P3 | Medium | Minor issue, workaround exists | 4 hours |
| P4 | Low | Cosmetic, enhancement | 24 hours |
| P5 | Backlog | Nice to have | Next sprint |

### Priority Calculation Factors
- **Impact:** How many users/systems affected?
- **Urgency:** How time-sensitive is the resolution?
- **Business value:** Revenue/customer impact?
- **SLA constraints:** Contractual response times?

## Escalation Rules

### Time-based Escalation
```json
{
  "escalation_rules": [
    {
      "after_hours": 2,
      "notify": ["manager_id"],
      "reassign_to": "$input.manager_id"
    },
    {
      "after_hours": 8,
      "notify": ["director_id"],
      "reassign_to": "$input.director_id"
    }
  ]
}
```

### Condition-based Escalation
Escalate if:
- Task unresolved after X hours
- Priority changes to higher level
- Customer follows up
- SLA breach imminent

## Assignment Best Practices

1. **Clear ownership:** Always assign to a user or group
2. **Set priorities:** Use consistent priority levels
3. **Add context:** Include description and steps to reproduce
4. **Set expectations:** Estimate resolution time
5. **Monitor progress:** Track time in each status
6. **Escalate appropriately:** Don't wait for SLA breach

## Natural Language to Assignment

| Description | Suggested Configuration |
|-------------|------------------------|
| "Assign to manager" | `{"assigned_to_user_id": "$input.manager_id"}` |
| "Route to support team" | `{"assigned_group_id": 5, "assignment_type": "round_robin"}` |
| "Critical issue, notify director" | Priority P1 + escalation after 1 hour |
| "Wait for customer response" | Status: pending_customer_feedback |

## API Integration

When generating task configurations via AI:

```json
{
  "step_type": "human_task",
  "definition": {
    "title": "Review Request",
    "description": "Please review the submitted request",
    "assigned_to_user_id": "$input.requester_manager",
    "priority": 2,
    "timeout_hours": 24,
    "escalation_rules": [
      {
        "after_hours": 12,
        "notify": ["admin"],
        "message": "Task approaching SLA deadline"
      }
    ]
  }
}
```

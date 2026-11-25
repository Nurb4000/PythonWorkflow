# Delay Node Knowledge Base

## Context
Delay nodes (`delay` and `programmable_delay`) pause workflow execution. Simple delays use a fixed duration; programmable delays support SQL-based waits and cron schedules.

## Generation Patterns

### Fixed Delay (seconds)
```json
{
  "seconds": 300
}
```

### Programmable Delay - Cron Schedule
```json
{
  "delay_type": "cron",
  "cron_expression": "0 9 * * 1"
}
```

### Programmable Delay - SQL Wait
```json
{
  "delay_type": "sql_wait",
  "query": "SELECT EXISTS(SELECT 1 FROM tasks WHERE id = $input.task_id AND status = 'completed')"
}
```

## Explanation Patterns
- Describe the delay duration or trigger condition.
- For cron: explain the schedule in plain English (e.g., "Every Monday at 9 AM").
- For SQL wait: explain what condition is being polled.

## Common Cron Expressions
- `*/5 * * * *` - Every 5 minutes
- `0 * * * *` - Every hour
- `0 9 * * *` - Daily at 9 AM
- `0 9 * * 1` - Monday at 9 AM
- `0 0 1 * *` - First of each month

## Fix Patterns
- Common errors: invalid cron syntax, negative seconds, SQL query always returns false.
- Suggest adding a timeout to SQL waits to prevent infinite loops.
- Validate cron expression format (5 fields: minute hour day month weekday).

## Safety Rules
- Maximum fixed delay: 86400 seconds (24 hours).
- SQL wait queries must be SELECT-only with a boolean result.
- Cron expressions are validated at runtime.

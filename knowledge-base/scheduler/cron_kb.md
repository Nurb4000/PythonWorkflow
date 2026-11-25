# Cron Expression Knowledge Base

## Purpose
Generate and validate cron expressions for workflow schedules.

## Cron Format

Standard 5-field cron expression:

```
┌───────────── minute (0 - 59)
│ ┌───────────── hour (0 - 23)
│ │ ┌───────────── day of month (1 - 31)
│ │ │ ┌───────────── month (1 - 12)
│ │ │ │ ┌───────────── day of week (0 - 7, Sunday = 0 or 7)
│ │ │ │ │
* * * * *
```

## Common Patterns

### Daily at Specific Time
```
0 9 * * *     # Daily at 9:00 AM
0 17 * * *    # Daily at 5:00 PM
```

### Weekly on Specific Day
```
0 9 * * 1     # Mondays at 9:00 AM
0 9 * * 5     # Fridays at 9:00 AM
0 9 * * 0     # Sundays at 9:00 AM
```

### Monthly on Specific Day
```
0 9 1 * *     # First day of month at 9:00 AM
0 9 15 * *    # 15th of month at 9:00 AM
```

### Specific Intervals
```
*/15 * * * *     # Every 15 minutes
*/30 * * * *     # Every 30 minutes
0 */2 * * *      # Every 2 hours
0 * * * *        # Every hour
```

### Weekdays Only
```
0 9 * * 1-5    # Monday to Friday at 9:00 AM
```

### Multiple Times
```
0 9,17 * * *   # Daily at 9 AM and 5 PM
0 8 * * 1,3,5  # Monday, Wednesday, Friday at 8 AM
```

## Natural Language to Cron

| Description | Cron Expression |
|-------------|-----------------|
| Every day at 9 AM | `0 9 * * *` |
| Every Monday at 8 AM | `0 8 * * 1` |
| First day of month at midnight | `0 0 1 * *` |
| Every 15 minutes | `*/15 * * * *` |
| Weekdays at 9 AM and 5 PM | `0 9,17 * * 1-5` |
| Last day of month | Use script to calculate |

## Timezone Considerations

Cron expressions use the configured timezone. Common timezones:

```
UTC
US/Eastern
US/Central
US/Mountain
US/Pacific
Europe/London
Europe/Paris
Asia/Tokyo
```

**Example:** "Daily at 9 AM EST" → `0 9 * * *` with timezone `US/Eastern`

## Validation Rules

1. **Minutes:** 0-59
2. **Hours:** 0-23
3. **Day of month:** 1-31
4. **Month:** 1-12
5. **Day of week:** 0-7 (0 and 7 = Sunday)

## Special Characters

| Character | Description | Example |
|-----------|-------------|---------|
| `*` | Any value | `*` in hour = every hour |
| `,` | List values | `1,3,5` = Monday, Wednesday, Friday |
| `-` | Range | `1-5` = days 1 through 5 |
| `/` | Step values | `*/15` = every 15 minutes |

## Examples with Explanations

### `0 9 * * 1-5`
- **When:** Monday through Friday at 9:00 AM
- **Use case:** Weekday morning reports

### `0 0 1 * *`
- **When:** First day of every month at midnight
- **Use case:** Monthly billing cycles

### `*/30 8-18 * * *`
- **When:** Every 30 minutes between 8 AM and 6 PM
- **Use case:** Business hours monitoring

### `0 6 * * 0`
- **When:** Sundays at 6:00 AM
- **Use case:** Weekend maintenance

## Testing Cron Expressions

Use online validators or test with:

```bash
# Check when next run is
croniter --next "0 9 * * *"

# Or use Python
from datetime import datetime
from dateutil.parser import parse
# Parse and calculate next occurrence
```

## Common Mistakes

1. **Wrong day of week:** 0 = Sunday, not Monday
2. **Off-by-one:** Minutes are 0-59, not 1-60
3. **Timezone confusion:** Always specify timezone explicitly
4. **Invalid ranges:** `1-5` means 1,2,3,4,5 not 1 through 5 inclusive

## Best Practices

1. **Comment complex expressions:** Add description in schedule name
2. **Test before relying:** Run manually first
3. **Use descriptive names:** "Weekly Report Monday 9AM" not "Schedule 1"
4. **Consider timezone:** Specify explicitly to avoid confusion
5. **Validate with tools:** Use cron validators before deploying

## API Integration

When generating schedules via AI:

```json
{
  "name": "Weekly Server Report",
  "cron_expression": "0 9 * * 1",
  "timezone": "US/Eastern",
  "description": "Every Monday at 9 AM EST"
}
```

## Troubleshooting

### Schedule not running
- Check timezone setting
- Verify cron expression is valid
- Ensure workflow is active
- Check schedule is enabled

### Wrong execution time
- Confirm timezone matches your location
- Remember: cron uses 24-hour format
- Day of week: 0 = Sunday, 6 = Saturday

### Conflicts with other schedules
- Check for overlapping times
- Stagger executions if possible
- Monitor resource usage

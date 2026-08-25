# Scheduler Configuration

**Version:** 1.0+  
**Last Updated:** 2026-08-25

---

## Overview

The **Scheduler** runs workflows automatically based on cron-like expressions. Use it for:

- **Recurring reports:** Generate and email reports daily/weekly
- **Data synchronization:** Sync data from external systems on schedule
- **Maintenance tasks:** Clean up old records, archive data
- **Monitoring:** Check system health at intervals

### Access
- **Admin:** `/admin/schedules` — Full scheduler management
- **Developer:** View own schedules

---

## Creating a Schedule

### 1. Navigate to Schedules

```
Admin → Schedules
```

### 2. Add New Schedule

Click **+ New Schedule**.

**Configuration:**

| Field | Description | Example |
|-------|-------------|---------|
| **Name** | Display name | "Daily Report" |
| **Workflow ID** | Workflow to execute | `12` |
| **Cron Expression** | When to run | `0 9 * * *` (daily at 9 AM) |
| **Timezone** | Schedule timezone | `UTC`, `US/Eastern` |
| **Enabled** | Active or paused | `true` |
| **Input Data** | JSON data passed to workflow | `{"report_type": "weekly"}` |

### 3. Save

Schedule is created in "enabled" state and runs immediately according to cron expression.

---

## Cron Expressions

Standard 5-field cron format:

```
┌───────────── minute (0 - 59)
│ ┌───────────── hour (0 - 23)
│ │ ┌───────────── day of month (1 - 31)
│ │ │ ┌───────────── month (1 - 12)
│ │ │ │ ┌───────────── day of week (0 - 6, Sunday = 0)
│ │ │ │ │
* * * * *
```

### Examples

| Expression | Description |
|------------|-------------|
| `0 9 * * *` | Daily at 9:00 AM |
| `0 9 * * 1` | Mondays at 9:00 AM |
| `*/15 * * * *` | Every 15 minutes |
| `0 0 1 * *` | First day of every month at midnight |
| `0 8 * * 1-5` | Weekdays (Mon-Fri) at 8:00 AM |
| `30 6 * * 1,3,5` | Monday, Wednesday, Friday at 6:30 AM |

**Timezone:** Schedules use the configured timezone. Convert cron expressions accordingly.

---

## Schedule States

### Enabled
Schedule runs according to cron expression.

### Disabled
Paused — does not run but retains configuration.

**Toggle:** Edit schedule → Enable/Disable switch

### Next Run Time
Displays when the schedule will next execute.

**Update:** After editing, next run time recalculates.

---

## Running Schedules

### Manual Trigger

1. Open schedule detail
2. Click **Run Now**
3. Workflow executes immediately

**Use case:** Test a schedule before relying on automation.

### View Run History

1. Open schedule detail
2. Click **Runs** tab
3. See:
   - Start time
   - End time
   - Status (success/failed)
   - Run ID (link to run inspector)

---

## Schedule Inputs

Pass data to scheduled workflows via the **Input Data** field.

**Format:** JSON object.

**Example:**
```json
{
  "report_type": "weekly",
  "recipients": ["admin@example.com"],
  "include_archived": false
}
```

**Access in workflow:** `$input.report_type`, `$input.recipients`, etc.

---

## Timezone Configuration

### System Timezone

Set in **Admin → Settings → Scheduler**.

**Default:** `UTC`

**Options:** Any IANA timezone (e.g., `US/Eastern`, `Europe/London`, `Asia/Tokyo`)

### Per-Schedule Timezone

Override system timezone for individual schedules.

**Use case:** Global schedules with local execution times.

---

## Monitoring

### Schedule Health

Monitor schedule reliability:

1. **Admin → Schedules** → View run history
2. Check for:
   - Consistent execution times
   - Failure patterns
   - Missed runs

### Alerts

Configure email alerts for schedule failures:

1. **Admin → Settings → Email**
2. Enable admin notifications
3. Set recipient email

**Alternatively:** Add a workflow step that sends alerts on failure.

---

## Troubleshooting

### Schedule not running

**Check:**
- Schedule is enabled
- Cron expression is valid
- Timezone is correct
- Workflow exists and is active
- No conflicting schedules

**Test:** Click "Run Now" to verify execution.

### Wrong execution time

**Check:**
- Timezone setting matches your location
- Cron expression uses correct timezone
- System clock is synchronized (NTP)

**Fix:** Update timezone in settings or per-schedule.

### Workflow fails during scheduled run

**Check:**
- Run inspector for error details
- Workflow logs
- Input data format

**Common issues:**
- Missing required fields in input data
- External service unavailable
- Database connection errors

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/admin/schedules` | List schedules |
| `POST` | `/admin/schedules` | Create schedule |
| `PUT` | `/admin/schedules/{id}` | Update schedule |
| `DELETE` | `/admin/schedules/{id}` | Delete schedule |
| `POST` | `/admin/schedules/{id}/test` | Test run schedule |
| `GET` | `/admin/schedules/status` | Active schedule status |

---

## Best Practices

1. **Test before relying:** Run schedules manually first
2. **Use descriptive names:** "Daily Report - Mondays" not "Schedule 1"
3. **Document inputs:** Comment JSON input data
4. **Monitor failures:** Set up alerts for failed runs
5. **Version control:** Track schedule changes in git
6. **Backup configs:** Export schedules before major changes
7. **Stagger runs:** Avoid running many schedules at same time

---

## Related Documentation

- [Workflow Designer](../features/workflows/designer.md)
- [Email Setup](./email-setup.md)
- [Monitoring and Logs](./monitoring.md)

---

*Next: [Backup Procedures](./backups.md)*

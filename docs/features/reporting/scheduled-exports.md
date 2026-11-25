# Scheduled Exports

**Version:** 1.0+  
**Last Updated:** 2026-08-25

---

## Overview

Automate report delivery via email or file export on a schedule. Use for:

- **Weekly summaries** to stakeholders
- **Monthly compliance** reports
- **Daily backups** of critical data
- **Real-time alerts** on specific conditions

---

## Creating a Scheduled Export

### 1. Define Report

Create or select an existing report (see [Reporting Overview](./overview.md)).

### 2. Configure Schedule

In report settings, navigate to **Schedule** tab:

| Setting | Description | Example |
|---------|-------------|---------|
| **Enable** | Turn scheduling on/off | `true` |
| **Cron Expression** | When to run | `0 9 * * 1` (Monday 9 AM) |
| **Timezone** | Schedule timezone | `UTC`, `US/Eastern` |
| **Format** | Output format | `csv`, `json`, `excel` |
| **Recipients** | Email addresses | `admin@example.com, boss@company.com` |
| **Subject** | Email subject line | `{report_name} - {date}` |
| **Body** | Email message | Custom template |
| **Attachment** | Include report file | `true` / `false` |

### 3. Test Schedule

Click **Run Now** to test without waiting for schedule.

**Verify:**
- Report generates correctly
- Email sends successfully
- Attachment is valid

### 4. Save Schedule

Click **Save**. Schedule is active immediately.

---

## Cron Expressions

Standard 5-field cron format:

```
┌───────────── minute (0 - 59)
│ ┌───────────── hour (0 - 23)
│ │ ┌───────────── day of month (1 - 31)
│ │ │ ┌───────────── month (1 - 12)
│ │ │ │ ┌───────────── day of week (0 - 7, Sunday = 0 or 7)
│ │ │ │ │
* * * * *
```

### Common Patterns

| Expression | Description |
|------------|-------------|
| `0 9 * * *` | Daily at 9:00 AM |
| `0 9 * * 1` | Mondays at 9:00 AM |
| `0 9 1 * *` | First of month at 9:00 AM |
| `*/30 * * * *` | Every 30 minutes |
| `0 0 * * 0` | Sundays at midnight |
| `0 8,17 * * 1-5` | Weekdays at 8 AM and 5 PM |

**Timezone:** Schedules use the configured timezone. Convert expressions accordingly.

---

## Email Delivery

### Recipient Management

**Add recipients:**
- Comma-separated emails in schedule configuration
- Or select from user list (if integrated)

**Remove recipients:**
- Edit schedule → delete email
- Or disable schedule entirely

### Email Template

Customize email content:

```
Subject: {report_name} - {date:YYYY-MM-DD}

Dear {recipient},

Please find attached the {report_name} report for the period 
{period_start} to {period_end}.

Summary:
- Total records: {record_count}
- Average value: {average_value}
- Trend: {trend_direction}

Questions? Contact admin@example.com.

Best regards,
Automated Reporting System
```

**Variables:**
- `{report_name}` — Report name
- `{date}` — Current date (format: `YYYY-MM-DD`)
- `{period_start}` — Start of reporting period
- `{period_end}` — End of reporting period
- `{record_count}` — Number of rows in report
- `{recipient}` — Email address of recipient

### Delivery Confirmation

Admin receives confirmation email when:
- Schedule runs successfully
- Schedule fails (with error details)

**Configure:** Admin → Settings → Email Notifications

---

## File Export

### Export Locations

Exported files are stored in:

```
backend/backend_data/exports/
├── reports/
│   ├── weekly_server_inventory_2026-08-25.csv
│   ├── monthly_compliance_2026-08-01.xlsx
│   └── daily_backup_2026-08-25.json
```

### Retention

Configure file retention:

| Setting | Default | Description |
|---------|---------|-------------|
| `export_retention_days` | 30 | Days to keep exported files |
| `export_cleanup_hour` | 3 AM | Time to run cleanup |

**Cleanup script:** Runs daily, deletes files older than retention period.

### Download Exports

Admins can download past exports:

1. Admin → Reports → Export History
2. Filter by date range
3. Click **Download** on desired export

---

## Monitoring Scheduled Exports

### View Schedule Status

1. Admin → Reports → Scheduled Exports
2. See:
   - **Next run time**
   - **Last run status** (success/failure)
   - **Run history** (last 10 executions)

### Alert on Failure

Configure email alerts for failed exports:

```python
# In settings
export_failure_alert_email = "ops@example.com"
export_failure_alert_threshold = 3  # Alert after 3 consecutive failures
```

### Log Analysis

Check backend logs for export errors:

```bash
docker compose logs backend | grep "export"
```

**Common errors:**
- SMTP delivery failure
- File generation timeout
- Permission denied on export directory

---

## Troubleshooting

### Export not running

**Check:**
- Schedule is enabled
- Cron expression is valid
- Timezone is correct
- No conflicting schedules

**Test:** Click "Run Now" to verify execution.

### Email not delivered

**Check:**
- SMTP settings configured (Admin → Settings → Email)
- Recipient emails are valid
- Email server is accessible

**Test:** Send test email from Settings page.

### Attachment missing

**Check:**
- Report generated successfully
- File size within limits (default: 10 MB)
- Format is supported

**Fix:** Reduce report size or increase limit in settings.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/reports/scheduled` | List scheduled exports |
| `POST` | `/reports/{id}/schedule` | Configure schedule |
| `PUT` | `/reports/{id}/schedule` | Update schedule |
| `DELETE` | `/reports/{id}/schedule` | Disable schedule |
| `POST` | `/reports/{id}/run-now` | Test run immediately |
| `GET` | `/reports/{id}/history` | View run history |

---

## Best Practices

1. **Start simple:** Begin with daily exports, adjust frequency as needed
2. **Test thoroughly:** Run manually before relying on automation
3. **Monitor delivery:** Check email logs weekly for failures
4. **Rotate retention:** Archive old exports to separate storage
5. **Document schedules:** Maintain a registry of all scheduled exports
6. **Backup configs:** Export schedule configurations regularly
7. **Review recipients:** Remove inactive emails quarterly

---

## Related Documentation

- [Reporting Overview](./overview.md)
- [Email Setup](../../administration/email-setup.md)
- [Backup Procedures](../../administration/backups.md)

---

*Next: [Bulk Operations](../bulk-operations.md)*

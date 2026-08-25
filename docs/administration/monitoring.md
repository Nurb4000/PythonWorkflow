# Monitoring and Logs

**Version:** 1.0+  
**Last Updated:** 2026-08-25

---

## Overview

Monitor system health, workflow execution, and application performance. View logs in real-time or export for analysis.

### Access
- **Admin Dashboard:** `/admin` → System Logs card
- **CLI:** `docker compose logs` commands
- **API:** `/admin/logs` endpoint

---

## Log Levels

| Level | Description | Example |
|-------|-------------|---------|
| **DEBUG** | Detailed diagnostic information | SQL queries, variable values |
| **INFO** | General informational messages | Workflow started, user logged in |
| **WARNING** | Potential issues | Slow queries, deprecated features |
| **ERROR** | Error conditions | Failed API calls, exceptions |
| **CRITICAL** | System failures | Database connection lost |

---

## Viewing Logs

### Admin Dashboard

1. Navigate to **Admin Dashboard**
2. Scroll to **System Logs** card
3. Click **View Logs**
4. Filter by:
   - **Level:** Error, Warning, Info, etc.
   - **Search term:** Keyword in log messages
   - **Time range:** Last hour, day, week

### CLI (Docker)

```bash
# All logs
docker compose logs

# Backend only
docker compose logs backend

# Frontend only
docker compose logs frontend

# PostgreSQL only
docker compose logs postgres

# Follow logs in real-time
docker compose logs -f

# Last N lines
docker compose logs --tail 100

# Specific time range
docker compose logs --since "2026-08-25T10:00:00" --until "2026-08-25T12:00:00"
```

### API Endpoint

```http
GET /admin/logs?level=error&search=workflow&limit=100
```

**Response:**
```json
{
  "logs": [
    {
      "timestamp": "2026-08-25T10:30:00Z",
      "level": "ERROR",
      "logger": "app.services.workflow_engine",
      "message": "Workflow execution failed: step 5 timeout"
    }
  ],
  "total": 42,
  "page": 1
}
```

---

## Log Export

### Export to File

```bash
docker compose logs --tail 1000 > logs_$(date +%Y%m%d).txt
```

### Export via API

```http
GET /admin/logs/export?format=csv&level=error&since=2026-08-25
```

**Formats:** `json`, `csv`, `text`

---

## Monitoring Workflow Executions

### Run Inspector

View detailed execution information for any workflow run:

1. Open workflow → **Runs** tab
2. Click run ID
3. See:
   - **Timeline:** Step execution order and duration
   - **Input/Output:** Data at each step
   - **Errors:** Failure details with stack traces
   - **Metadata:** Start/end times, user, tags

### Run Statistics

Track workflow performance over time:

- **Success rate:** % of runs completing without errors
- **Average duration:** Time from start to finish
- **Failure patterns:** Common error types and frequencies
- **Peak usage:** When workflows run most often

**View:** Admin Dashboard → Workflow Statistics card

---

## Alerting

### Email Alerts

Configure admin notifications for:
- Workflow failures
- Schedule execution errors
- System errors (500s)

**Setup:** Admin → Settings → Email Configuration

### Webhook Alerts

Send alerts to external systems (Slack, PagerDuty, etc.):

1. Create workflow with webhook step
2. Configure webhook URL
3. Trigger on specific events

**Example:** Slack integration via webhook URL.

---

## Performance Monitoring

### Database Queries

Monitor slow queries:

```sql
-- Find queries taking >1 second
SELECT query, calls, mean_exec_time
FROM pg_stat_statements
WHERE mean_exec_time > 1000
ORDER BY mean_exec_time DESC;
```

**View in:** Admin Dashboard → Database Stats (if enabled)

### API Response Times

Track endpoint performance:

```bash
# Measure response time for API endpoint
time curl -s http://localhost:6000/api/workflows
```

**View in:** Admin Dashboard → API Stats (if enabled)

### Resource Usage

Monitor container resource consumption:

```bash
docker stats
```

**Key metrics:**
- CPU usage (%)
- Memory usage (MB)
- Network I/O (KB/s)
- Block I/O (KB/s)

---

## Log Retention

### Default Retention

- **Application logs:** 30 days (configurable)
- **Database logs:** Until manual cleanup
- **Backup logs:** Per backup retention policy

### Configure Retention

Edit `backend/app/core/config.py`:

```python
log_retention_days: int = 30
```

### Cleanup Old Logs

```bash
# Remove logs older than 30 days
find /var/log/pythonworkflow -name "*.log" -mtime +30 -delete

# Or via API (if implemented)
DELETE /admin/logs/cleanup?older_than_days=30
```

---

## Troubleshooting with Logs

### Workflow Fails to Execute

**Check logs for:**
- Step execution errors
- Timeout exceptions
- Permission denied messages

**Example:**
```
ERROR app.services.workflow_engine - Step 5 failed: HTTP 500 from external API
```

### Slow Performance

**Check logs for:**
- Long-running queries
- Timeout warnings
- Resource exhaustion

**Example:**
```
WARNING app.services.database - Query took 5.2s: SELECT * FROM large_table
```

### Authentication Issues

**Check logs for:**
- LDAP bind failures
- Invalid credentials
- Token expiration

**Example:**
```
ERROR app.api.auth - LDAP bind failed: invalid credentials for cn=admin,dc=example,dc=com
```

---

## Related Documentation

- [Backup Procedures](./backups.md)
- [Email Setup](./email-setup.md)
- [Scheduler Configuration](./scheduler.md)

---

*Next: [Environment Promotion](./environment-promotion.md)*

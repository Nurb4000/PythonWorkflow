# Reporting Overview

**Version:** 1.0+  
**Last Updated:** 2026-08-25

---

## Overview

The **Reporting System** provides tools for creating, scheduling, and exporting reports from workflow data, form submissions, and CI items.

### Report Types

| Type | Description | Use Case |
|------|-------------|----------|
| **SQL View Reports** | Based on auto-generated SQL VIEWs | Standard operational reports |
| **Custom Reports** | User-defined queries via Data Explorer | Ad-hoc analysis |
| **Scheduled Exports** | Automated CSV/JSON delivery | Regular stakeholder updates |
| **Dashboard Cards** | Embedded report visualizations | Real-time monitoring |

---

## Creating a Report

### 1. Define Report

Navigate to **Admin → Reports → + New Report**.

**Configuration:**

| Field | Description |
|-------|-------------|
| **Name** | Display name (e.g., "Weekly Server Inventory") |
| **Description** | Purpose and audience |
| **Source** | SQL VIEW, custom query, or form submission |
| **Columns** | Fields to include |
| **Filters** | WHERE conditions |
| **Sort** | ORDER BY clause |
| **Limit** | Maximum rows |

### 2. Configure Output

- **Format:** CSV, JSON, Excel
- **Schedule:** Cron expression for automated runs
- **Recipients:** Email addresses for delivery
- **Attachment:** Include report as email attachment

### 3. Save and Test

Click **Save Report**. Test by running manually.

---

## Report Sources

### SQL VIEW Reports

Use auto-generated views from forms and CI types.

**Example:** Report on all active servers.

```sql
SELECT name, ip_address, os, location 
FROM v_ci_server 
WHERE status = 'active' 
ORDER BY name;
```

**Benefits:**
- Pre-structured data
- Consistent column names
- Automatic regeneration on schema changes

### Custom Query Reports

Build queries using the Visual Query Builder.

**Access:** `/data-explorer` → Saved Queries → Export as report

**Benefits:**
- Flexible filtering
- Aggregations
- Join multiple tables

### Form Submission Reports

Aggregate data from form submissions.

**Example:** Monthly request volume by type.

```sql
SELECT form_id, COUNT(*) as submission_count, 
       AVG(rating) as avg_rating
FROM v_form_request_submission
WHERE submitted_at > NOW() - INTERVAL '30 days'
GROUP BY form_id;
```

---

## Scheduled Exports

### Configuration

1. Open report
2. Click **Schedule** tab
3. Set cron expression (e.g., `0 9 * * 1` for Monday 9 AM)
4. Add recipients
5. Choose format
6. Save

### Delivery

Reports are:
1. Generated at scheduled time
2. Attached to email
3. Sent to configured recipients
4. Logged in admin dashboard

### Email Template

Customize email content:

```
Subject: {report_name} - {date}

Body:
Please find attached the {report_name} report for {period}.

Questions? Contact admin@example.com.
```

---

## Dashboard Cards

Embed reports as cards on the Admin Dashboard.

**Steps:**
1. Admin → Dashboard → Edit Layout
2. Click **+ Add Card**
3. Select report
4. Configure display (table, chart, KPI)
5. Save

**Card Types:**
- **Table:** Raw data rows
- **Chart:** Bar, line, pie visualizations
- **KPI:** Single metric with trend

---

## Report Permissions

| Role | Access |
|------|--------|
| **Admin** | Create, edit, delete, schedule all reports |
| **Developer** | View and run own reports |
| **Staff/User** | View shared reports only |

**Share reports:** Admin can mark reports as "shared" for specific groups.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/reports` | List reports |
| `POST` | `/reports` | Create report |
| `PUT` | `/reports/{id}` | Update report |
| `DELETE` | `/reports/{id}` | Delete report |
| `POST` | `/reports/{id}/run` | Execute report manually |
| `GET` | `/reports/{id}/export` | Export current results |
| `POST` | `/reports/{id}/schedule` | Configure schedule |

---

## Best Practices

1. **Name clearly:** "Weekly Server Inventory - Active" not "Report 1"
2. **Document purpose:** Add description for each report
3. **Test schedules:** Run manually before automating
4. **Limit recipients:** Only share with those who need it
5. **Monitor delivery:** Check email logs for failures
6. **Archive old reports:** Delete unused scheduled exports
7. **Version control:** Track report definitions in git

---

## Related Documentation

- [SQL Views](../data-explorer/sql-views.md)
- [Visual Query Builder](../data-explorer/visual-builder.md)
- [Scheduled Exports](./scheduled-exports.md)

---

*Next: [Scheduled Exports](./scheduled-exports.md)*

# Scheduling & Triggers - Phase 4

## Overview
Phase 4 adds comprehensive scheduling and trigger capabilities to the workflow system, including cron-based scheduling, webhook triggers, and external API triggers.

## Features Implemented

### 1. Cron-Based Scheduling
- **5-part cron expressions**: `minute hour day month day_of_week`
- **Validation**: Server-side validation of cron expressions
- **Management**: Create, update, enable/disable, delete schedules
- **Testing**: Manual test trigger for schedules

### 2. Webhook Triggers
- **Endpoint**: `POST /api/webhook/{workflow_id}`
- **Authentication**: Optional `X-Webhook-Secret` header
- **Payload**: Any JSON payload is passed to the workflow as input data
- **Use Case**: External system notifications, event-driven workflows

### 3. External API Triggers
- **Endpoint**: `POST /api/api/trigger/{workflow_id}`
- **Authentication**: Optional `X-API-Key` header
- **Input Data**: Custom JSON payload
- **Use Case**: Integration with other systems, programmatic triggers

### 4. Schedule Management
- **List**: View all schedules with status
- **Create**: Add new schedules with cron expressions
- **Update**: Modify cron expressions and enable/disable
- **Delete**: Remove schedules
- **Test**: Manually trigger a schedule to test configuration

## API Endpoints

### Webhooks
```
POST /api/webhook/{workflow_id}
Headers: X-Webhook-Secret: <secret>
Body: { "event": "...", "data": {...} }
```

### External API
```
POST /api/api/trigger/{workflow_id}
Headers: X-API-Key: <key>
Body: { "input_data": {...} }
```

### Schedule Management
```
GET    /api/admin/schedules              - List all schedules
POST   /api/admin/schedules              - Create schedule
PUT    /api/admin/schedules/{id}         - Update schedule
DELETE /api/admin/schedules/{id}         - Delete schedule
POST   /api/admin/schedules/{id}/test    - Test trigger schedule
GET    /api/webhook/schedules/status     - Get active schedule status
```

## Cron Expression Examples

| Expression | Description |
|------------|-------------|
| `0 0 * * *` | Daily at midnight |
| `0 8 * * 1-5` | Weekdays at 8 AM |
| `*/15 * * * *` | Every 15 minutes |
| `0 0 * * 0` | Sundays at midnight |
| `30 9 1 * *` | 1st of every month at 9:30 AM |
| `0 */2 * * *` | Every 2 hours |

## Schedule Status

Schedules can be in two states:
- **Enabled**: Actively scheduled and will run automatically
- **Disabled**: Won't run until re-enabled

## Testing Workflows

### Test via Web UI
1. Navigate to Admin Dashboard
2. Click "+ New Schedule"
3. Enter workflow ID and cron expression
4. Click "Test" to trigger immediately

### Test via API
```bash
# Test webhook
curl -X POST http://localhost:8000/api/webhook/1 \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: mysecret" \
  -d '{"test": true}'

# Test external API
curl -X POST http://localhost:8000/api/api/trigger/1 \
  -H "Content-Type: application/json" \
  -H "X-API-Key: mykey" \
  -d '{"input_data": {"manual": true}}'
```

## Security Considerations

1. **Webhook Authentication**: Use `X-Webhook-Secret` header to verify requests
2. **API Key Authentication**: Use `X-API-Key` header for external triggers
3. **Workflow Validation**: Only active workflows can be triggered
4. **Rate Limiting**: Consider implementing rate limits for webhook endpoints

## Integration Examples

### GitHub Webhook
```json
{
  "event": "push",
  "repository": "user/repo",
  "ref": "refs/heads/main"
}
```

### Stripe Webhook
```json
{
  "event": "payment.success",
  "data": {
    "customer_id": "cus_123",
    "amount": 100.00
  }
}
```

### Custom Integration
```json
{
  "action": "create_user",
  "email": "user@example.com",
  "name": "John Doe"
}
```

## Next Steps

- [ ] Add rate limiting for webhook endpoints
- [ ] Implement webhook signature verification
- [ ] Add schedule execution history
- [ ] Create UI for visual cron expression builder
- [ ] Add email notifications for schedule failures

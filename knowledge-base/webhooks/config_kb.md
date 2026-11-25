# Webhook Configuration Knowledge Base

## Purpose
Assist with webhook setup, validation, and configuration.

## Webhook Types

### Outgoing Webhooks (Workflow → External)
Triggered by workflow steps to send data to external systems.

**Configuration:**
```json
{
  "step_type": "webhook",
  "definition": {
    "method": "POST",
    "url": "https://api.example.com/webhook",
    "headers": {
      "Content-Type": "application/json",
      "Authorization": "Bearer ${WEBHOOK_SECRET}"
    },
    "body": "{\"event\": \"workflow_completed\", \"data\": $input}",
    "timeout": 30,
    "retry_count": 3,
    "retry_delay": 5
  }
}
```

### Incoming Webhooks (External → Workflow)
Trigger workflows when external systems send data.

**Configuration:**
```json
{
  "workflow_id": 42,
  "webhook_secret": "your-secret-here",
  "allowed_methods": ["POST"],
  "content_type": "application/json"
}
```

**Endpoint:** `POST /webhook/{workflow_id}?secret={webhook_secret}`

## URL Validation

### Valid URL Patterns
- `https://api.example.com/webhook`
- `http://localhost:8080/callback`
- `https://hooks.slack.com/services/xxx/yyy/zzz`

### Invalid URL Patterns
- `api.example.com/webhook` (missing protocol)
- `https://` (incomplete)
- `ftp://example.com` (unsupported protocol)

### Validation Rules
1. Must start with `http://` or `https://`
2. Must have valid domain or IP
3. Optional path and query parameters
4. Max length: 2048 characters

## Security Best Practices

### Outgoing Webhooks
- **Use HTTPS** whenever possible
- **Validate responses** — check status codes
- **Handle errors** — implement retry logic
- **Log requests** — for debugging and auditing

### Incoming Webhooks
- **Require secret** — Verify HMAC signature
- **Limit methods** — Only allow POST (or needed methods)
- **Rate limit** — Prevent abuse
- **Validate payload** — Check structure before processing

## Secret Management

### Generating Secrets
```python
import secrets
secret = secrets.token_urlsafe(32)
# Example: "k8s9f2j3h4g5d6s7a8p9o0i1u2y3t4r5"
```

### Storing Secrets
- **Environment variables:** `WEBHOOK_SECRET=xxx`
- **System settings:** Encrypted in database
- **Never hardcode** in workflow definitions

### Verifying Signatures (HMAC)
```python
import hmac
import hashlib

def verify_signature(payload, secret, signature):
    expected = hmac.new(
        secret.encode(), 
        payload.encode(), 
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
```

## Common Use Cases

### Slack Integration
```json
{
  "url": "https://hooks.slack.com/services/your-team-id/your-bot-id/your-webhook-url",
  "body": "{\"text\": \"Workflow completed: $input.workflow_name\"}"
}
```

### Email Notification
```json
{
  "url": "https://api.mailgun.net/v3/example.com/messages",
  "headers": {
    "Authorization": "Basic ${MAILGUN_API_KEY}"
  },
  "body": {
    "from": "Workflow <noreply@example.com>",
    "to": "$input.recipient_email",
    "subject": "Workflow Completed",
    "text": "Your workflow has finished."
  }
}
```

### Database Update
```json
{
  "url": "https://api.example.com/database/update",
  "method": "PUT",
  "body": "{\"id\": $input.record_id, \"status\": \"completed\"}"
}
```

### Webhook to Webhook (Chain)
```json
{
  "url": "https://api.example.com/forward",
  "body": "{\"source\": \"workflow\", \"data\": $input}"
}
```

## Testing Webhooks

### Outgoing
1. Use webhook.site or requestbin.com for testing
2. Check response status codes
3. Verify payload structure
4. Test with invalid URLs

### Incoming
1. Use curl to simulate requests:
   ```bash
   curl -X POST http://localhost:6000/webhook/42?secret=xxx \
     -H "Content-Type: application/json" \
     -d '{"test": true}'
   ```
2. Check workflow execution
3. Verify data processing
4. Test with missing/invalid secrets

## Error Handling

### Common Errors
| Error | Cause | Solution |
|-------|-------|----------|
| 401 Unauthorized | Invalid secret | Verify webhook_secret matches |
| 404 Not Found | Wrong URL | Check URL and path |
| 405 Method Not Allowed | Wrong HTTP method | Use allowed methods |
| 429 Too Many Requests | Rate limited | Implement backoff |
| 500 Server Error | Backend issue | Check logs |

### Retry Logic
```json
{
  "retry_count": 3,
  "retry_delay": 5,
  "retry_on": [429, 500, 502, 503, 504]
}
```

## Logging and Monitoring

### Log Entries
- Webhook triggered (incoming)
- Webhook executed (outgoing)
- Response status code
- Execution time
- Errors with stack traces

### Metrics to Track
- Success rate
- Average response time
- Error rates by type
- Volume over time

## API Reference

### Create Incoming Webhook
```http
POST /api/workflows/{id}/webhooks
{
  "secret": "generated-secret",
  "allowed_methods": ["POST"],
  "content_type": "application/json"
}
```

### Test Outgoing Webhook
```http
POST /api/webhooks/test
{
  "url": "https://example.com/webhook",
  "method": "POST",
  "body": {"test": true}
}
```

### List Webhooks
```http
GET /api/workflows/{id}/webhooks
```

## Best Practices

1. **Use HTTPS** for all webhooks
2. **Validate secrets** — Never trust incoming data
3. **Log everything** — For debugging and auditing
4. **Test thoroughly** — Use staging environments
5. **Handle errors** — Implement retry logic
6. **Monitor performance** — Track response times
7. **Document endpoints** — Keep webhook docs updated
8. **Rotate secrets** — Regularly update webhook secrets

## Troubleshooting

### Webhook not triggering
- Check workflow is active
- Verify webhook URL is correct
- Ensure secret matches
- Check network connectivity

### Invalid response
- Validate payload structure
- Check content-type headers
- Verify authentication
- Review error logs

### Timeout errors
- Increase timeout value
- Optimize external service
- Implement async processing
- Use message queues

### Security concerns
- Enable HTTPS
- Validate signatures
- Rate limit requests
- Monitor for anomalies

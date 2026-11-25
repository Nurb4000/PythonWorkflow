# Webhook Node Knowledge Base

## Context
Webhook nodes (`webhook`) send HTTP requests to external endpoints, typically for notifying other systems about workflow events. They support POST and GET methods with configurable timeout.

## Generation Patterns

### Event Notification Webhook
```json
{
  "url": "https://hooks.example.com/workflow-events",
  "method": "POST",
  "timeout": 30,
  "body": "{\"event\": \"workflow_completed\", \"run_id\": \"$input.run_id\", \"status\": \"$input.status\", \"timestamp\": \"$input.timestamp\"}"
}
```

### Slack/Discord Integration
```json
{
  "url": "${SLACK_WEBHOOK_URL}",
  "method": "POST",
  "timeout": 15,
  "body": "{\"text\": \"Workflow completed: $input.workflow_name | Status: $input.status\"}"
}
```

### Data Sync Webhook
```json
{
  "url": "https://api.example.com/sync/webhook",
  "method": "POST",
  "timeout": 60,
  "body": "{\"record_id\": \"$input.record_id\", \"changes\": $input.changes_json}"
}
```

## Explanation Patterns
- Describe the target URL, HTTP method, payload structure, and timeout.
- Identify `$input.*` variable references in the body.

## Fix Patterns
- Common errors: connection timeout, 4xx/5xx responses, invalid JSON body.
- Suggest increasing timeout for slow endpoints.
- Suggest verifying body is valid JSON string.

## Safety Rules
- SSRF protection applies: private IPs are blocked.
- URLs must use HTTPS when possible.
- Never hardcode real webhook URLs with tokens -- use `${VARIABLE_NAME}` placeholders.
- Timeout defaults to 30 seconds, max recommended 120 seconds.

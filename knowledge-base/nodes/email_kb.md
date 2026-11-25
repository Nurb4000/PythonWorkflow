# Email Node Knowledge Base

## Context
Email nodes (`email`) send notifications via SMTP. They support variable interpolation using `$input.*` syntax in the to, subject, and body fields.

## Generation Patterns

### Simple Notification
```json
{
  "to": "$input.user_email",
  "subject": "Your order has been confirmed",
  "body": "Hello $input.customer_name,\n\nYour order #$input.order_id has been confirmed.\nTotal: $input.order_total\n\nThank you!"
}
```

### Multi-recipient Email
```json
{
  "to": "$input.user_email, $input.manager_email",
  "subject": "Approval Request: $input.task_title",
  "body": "A new approval request requires your attention.\n\nTask: $input.task_title\nRequester: $input.requester_name\nAmount: $input.amount\n\nPlease review in the portal."
}
```

### HTML Email
```json
{
  "to": "$input.user_email",
  "subject": "Weekly Report Summary",
  "body": "<h1>Weekly Report</h1><p>Completed tasks: $input.completed_count</p><p>Pending: $input.pending_count</p>"
}
```

## Explanation Patterns
- Describe the recipient pattern, subject line purpose, and body content.
- Identify all `$input.*` variable references.

## Fix Patterns
- Common errors: invalid email address, missing SMTP configuration, undefined variable reference.
- Suggest using `.get()` patterns for optional fields in custom code before the email step.
- Remind that `$input.field` must be populated by an upstream step.

## Safety Rules
- Email addresses are validated at send time.
- Body content is limited to prevent abuse.
- SMTP credentials are stored in system settings, never in the node configuration.

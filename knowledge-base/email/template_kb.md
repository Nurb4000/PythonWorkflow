# Email Template Knowledge Base

## Purpose
Generate and manage email templates for workflow notifications.

## Template Structure

### Basic Template
```json
{
  "name": "Welcome Email",
  "subject": "Welcome to {company}!",
  "body_html": "<h1>Welcome {user_name}</h1><p>Get started with...</p>",
  "body_text": "Welcome {user_name}\n\nGet started with...",
  "from": "noreply@{company}.com",
  "reply_to": "support@{company}.com",
  "variables": ["user_name", "company", "login_url"]
}
```

### Template Variables
Common variables used in templates:

| Variable | Description | Example |
|----------|-------------|---------|
| `{user_name}` | Recipient's full name | John Doe |
| `{user_email}` | Recipient's email | john@example.com |
| `{company}` | Company name | Acme Corp |
| `{workflow_name}` | Workflow that triggered email | Employee Onboarding |
| `{task_title}` | Task description | Approve Request |
| `{link}` | Action URL | https://.../approve/123 |
| `{date}` | Current date | 2026-08-25 |
| `{time}` | Current time | 14:30 UTC |

## Template Types

### Transactional Emails
Triggered by specific events:
- Welcome emails
- Password reset
- Task assignments
- Approval requests
- Completion notifications

### Bulk/Marketing Emails
Scheduled or manual sends:
- Weekly reports
- Newsletter
- Announcements
- Training reminders

### Alert Emails
System-generated notifications:
- SLA breaches
- Error notifications
- Security alerts
- Maintenance warnings

## Writing Guidelines

### Subject Lines
- Keep under 50 characters
- Be specific about content
- Include action required if applicable
- Avoid spam trigger words

**Good:** "Action Required: Approve Expense Report #12345"  
**Bad:** "Important Update Regarding Your Recent Submission"

### Body Content
- Use HTML for rich formatting
- Include plain text fallback
- Add company branding (logo, colors)
- Include clear call-to-action
- Add unsubscribe link for bulk emails

### Best Practices
1. **Test variables:** Ensure all placeholders have defaults
2. **Mobile-friendly:** Use responsive design
3. **Accessible:** Proper heading hierarchy, alt text
4. **Legal compliance:** CAN-SPAM, GDPR where applicable
5. **Tracking:** Add UTM parameters for marketing emails

## Template Management

### Versioning
Track template changes:
```json
{
  "version": 2,
  "changes": "Updated subject line and added company logo",
  "changed_by": "admin@example.com",
  "changed_at": "2026-08-25T10:00:00Z"
}
```

### A/B Testing
Test multiple template variants:
```json
{
  "test_id": "welcome-email-v1-vs-v2",
  "variants": [
    {"name": "v1", "template_id": 1, "weight": 50},
    {"name": "v2", "template_id": 2, "weight": 50}
  ],
  "metrics": ["open_rate", "click_rate", "conversion"]
}
```

## AI Assistance Prompts

### Generate Template
"Create a welcome email template for new employee onboarding"

### Improve Template
"Improve this subject line: 'Your task needs attention'"

### Add Variables
"What variables should I include in an approval request email?"

### Translate
"Translate this template to Spanish: [template content]"

## Output Format

AI responses should include:
- Template name
- Subject line
- HTML body
- Plain text fallback
- List of required variables
- Any notes about customization

Example:
```json
{
  "name": "Task Assignment Notification",
  "subject": "New Task Assigned: {task_title}",
  "body_html": "<h2>You have a new task</h2><p>{task_description}</p><a href='{task_link}'>View Task</a>",
  "body_text": "You have a new task: {task_title}\n\n{task_description}\n\nView at: {task_link}",
  "variables": ["task_title", "task_description", "task_link", "assignee_name"],
  "notes": "Customize subject line and add company branding"
}
```

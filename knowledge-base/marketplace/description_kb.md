# Marketplace Description Knowledge Base

## Purpose
Generate compelling marketplace item descriptions, suggestions, and categorization.

## Item Types

### Workflow Packages
Complete workflow templates for common automation scenarios.

**Structure:**
```json
{
  "item_type": "workflow",
  "name": "Employee Onboarding",
  "description": "Automated employee onboarding workflow...",
  "category": "hr",
  "tags": ["onboarding", "hr", "automation"],
  "version": "1.0",
  "steps": [...]
}
```

### Node Templates
Reusable step configurations for common patterns.

**Structure:**
```json
{
  "item_type": "node",
  "name": "Slack Notification",
  "description": "Send Slack message with formatted embed...",
  "step_type": "api_call",
  "tags": ["slack", "notification", "messaging"]
}
```

## Description Writing Guidelines

### Best Practices
1. **Lead with value:** What does this accomplish?
2. **Be specific:** Mention exact capabilities
3. **Include use cases:** When should someone use this?
4. **Note requirements:** Any dependencies or prerequisites?
5. **Keep it scannable:** Use bullet points for key features

### Example: Good Description
```
Automated employee onboarding workflow that:
- Creates user accounts across systems
- Assigns appropriate groups and permissions
- Sends welcome email with first-day instructions
- Creates calendar events for orientation sessions
- Assigns training modules based on role

Requires: Active Directory, Office 365, and calendar system access.
```

### Example: Poor Description
```
This is a workflow for onboarding employees.
```

## Category Suggestions

| Category | Best For |
|----------|----------|
| `hr` | Employee lifecycle, recruitment, offboarding |
| `it` | Infrastructure, helpdesk, asset management |
| `finance` | Invoicing, expense reports, budget approval |
| `security` | Access control, incident response, compliance |
| `operations` | Daily operations, monitoring, maintenance |
| `development` | CI/CD, code review, deployment |
| `sales` | Lead processing, quote generation, CRM sync |
| `support` | Ticket routing, SLA tracking, customer comms |

## Tag Recommendations

### Common Tags
- `automation`, `approval`, `notification`, `integration`
- `hr`, `it`, `finance`, `security`
- `template`, `starter`, `advanced`
- `slim`, `enterprise`, `customizable`

### Tag Rules
1. Use lowercase
2. Separate multi-word with hyphens: `employee-onboarding`
3. Limit to 5-10 tags per item
4. Include both broad and specific tags

## AI Assistance Prompts

### Generate Description
"Write a marketplace description for an employee onboarding workflow that creates AD accounts, assigns groups, and sends welcome emails"

### Suggest Categories
"What category and tags should I use for a workflow that processes expense reports?"

### Improve Existing Description
"Improve this description: 'Workflow for approvals'"

### Generate Name
"Suggest 5 names for a workflow that monitors server health and alerts on issues"

## Output Format

AI responses should include:
- Generated description (3-5 sentences)
- Suggested category
- Recommended tags (5-10)
- Version number (if generating new item)
- Any notes about requirements or dependencies

Example:
```json
{
  "description": "Automated expense report processing workflow that:\n- Validates receipts against policy\n- Routes for approval based on amount\n- Integrates with accounting system\n- Sends status notifications to submitter",
  "category": "finance",
  "tags": ["expense", "approval", "accounting", "automation", "finance"],
  "suggested_names": [
    "Expense Report Processor",
    "Automated Expense Approval",
    "Finance Workflow Starter"
  ]
}
```

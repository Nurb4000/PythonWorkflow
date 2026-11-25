# Form Schema Knowledge Base

## Context
Form schemas define data collection interfaces using JSON Schema. Forms are used in workflow steps to gather user input, and can be embedded in human tasks and approvals.

## Field Types
- `string` - Text input (short/medium/long)
- `number` - Decimal values
- `integer` - Whole numbers
- `boolean` - Yes/No checkboxes
- `email` - Email address with validation
- `date` - Date picker
- `date-time` - Date and time picker
- `textarea` - Multi-line text
- `select` - Dropdown with options
- `file` - File upload
- `info` - Read-only informational text

## Generation Patterns

### Contact Form
```json
{
  "type": "object",
  "properties": {
    "full_name": {"type": "string", "title": "Full Name", "required": true},
    "email": {"type": "email", "title": "Email Address", "required": true},
    "phone": {"type": "string", "title": "Phone Number", "pattern": "^\\+?[0-9]{7,15}$"},
    "message": {"type": "textarea", "title": "Message", "required": true}
  },
  "required": ["full_name", "email", "message"]
}
```

### Expense Report Form
```json
{
  "type": "object",
  "properties": {
    "amount": {"type": "number", "title": "Amount", "required": true},
    "category": {"type": "select", "title": "Category", "options": ["Travel", "Meals", "Supplies", "Software"], "required": true},
    "date": {"type": "date", "title": "Expense Date", "required": true},
    "description": {"type": "textarea", "title": "Description"},
    "receipt": {"type": "file", "title": "Receipt Image"}
  },
  "required": ["amount", "category", "date"]
}
```

## Explanation Patterns
- List each field with its type, purpose, and validation rules.
- Note which fields are required vs optional.

## Fix Patterns
- Common errors: invalid field type, missing required property, broken regex pattern.
- Suggest adding validation (minLength, maxLength, pattern) for string fields.
- Remind that `required` array must match property names exactly.

## Safety Rules
- Field types must be from the allowed list above.
- Regex patterns should not use catastrophic backtracking.
- File uploads are handled by the platform's storage configuration.

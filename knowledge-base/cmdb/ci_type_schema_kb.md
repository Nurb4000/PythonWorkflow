# CI Type Schema Knowledge Base

## Purpose
Generate and validate CI type field schemas using AI assistance.

## CI Type Field Types

### Standard Field Types
| Type | Description | Example |
|------|-------------|---------|
| `string` | Single-line text | Hostname, IP address |
| `text` | Multi-line text | Description, notes |
| `number` | Numeric value | CPU cores, memory (GB) |
| `integer` | Whole number | Port number, quantity |
| `boolean` | True/false | Is active, is managed |
| `select` | Dropdown with options | Status, location |
| `date` | Date only | Purchase date, warranty expiry |
| `datetime` | Date and time | Last audit, next maintenance |
| `email` | Email address | Owner email, support email |
| `url` | Website URL | Documentation link, portal URL |
| `lookup` | Search and select | Owner (user lookup), parent CI |

### Field Configuration

Each field in a CI type schema has:

```json
{
  "key": "hostname",
  "label": "Host Name",
  "type": "string",
  "required": true,
  "help_text": "Fully qualified domain name or IP address",
  "options": [],
  "validation": {
    "min_length": 1,
    "max_length": 255,
    "pattern": "^[a-zA-Z0-9.-]+$"
  }
}
```

## Common CI Type Patterns

### Server
```json
{
  "fields": [
    {"key": "hostname", "label": "Hostname", "type": "string", "required": true},
    {"key": "ip_address", "label": "IP Address", "type": "string", "required": true},
    {"key": "os", "label": "Operating System", "type": "select", "options": ["Ubuntu", "CentOS", "Windows"]},
    {"key": "location", "label": "Location", "type": "string"},
    {"key": "owner", "label": "Owner", "type": "lookup", "lookup_config": {"target_type": "users"}}
  ]
}
```

### Application
```json
{
  "fields": [
    {"key": "app_name", "label": "Application Name", "type": "string", "required": true},
    {"key": "version", "label": "Version", "type": "string"},
    {"key": "owner_team", "label": "Owner Team", "type": "string"},
    {"key": "status", "label": "Status", "type": "select", "options": ["Development", "Staging", "Production", "Retired"]}
  ]
}
```

### Network Device
```json
{
  "fields": [
    {"key": "device_name", "label": "Device Name", "type": "string", "required": true},
    {"key": "ip_address", "label": "Management IP", "type": "string"},
    {"key": "device_type", "label": "Type", "type": "select", "options": ["Router", "Switch", "Firewall", "AP"]},
    {"key": "location", "label": "Location", "type": "string"},
    {"key": "serial_number", "label": "Serial Number", "type": "string"}
  ]
}
```

## Validation Rules

### String Validation
- `min_length`: Minimum character count
- `max_length`: Maximum character count
- `pattern`: Regex pattern to match

### Number Validation
- `min`: Minimum value
- `max`: Maximum value
- `step`: Increment for number inputs

### Select Validation
- `options`: Array of allowed values
- `multiple`: Allow multiple selections (boolean)

## Best Practices

1. **Use consistent keys:** Lowercase with underscores (e.g., `ip_address`, not `IP Address`)
2. **Add help text:** Explain what each field is for
3. **Set required appropriately:** Only mark truly mandatory fields as required
4. **Use lookups for references:** Reference users, other CIs via lookup type
5. **Document options:** For select fields, document all allowed values
6. **Consider future use:** Will this field be used in reports? Add to Field Library if yes

## AI Assistance Prompts

### Generate Schema
"Generate a CI type schema for [description]"

Example: "Generate a CI type schema for database servers"

### Validate Schema
"Validate this CI type schema: [JSON]"

### Suggest Fields
"What fields should I include for a [CI type]?"

Example: "What fields should I include for a network switch?"

## Output Format

AI responses should be valid JSON matching the CI type schema structure:

```json
{
  "key": "database_server",
  "name": "Database Server",
  "description": "Physical or virtual database servers",
  "icon": "🗄️",
  "fields": [
    { /* field definitions */ }
  ]
}
```

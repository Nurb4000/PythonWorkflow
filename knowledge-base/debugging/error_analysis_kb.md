# Error Analysis Knowledge Base

## Context
This KB helps diagnose workflow run failures by analyzing error messages, step configurations, and execution context.

## Common Failure Patterns

### Database Query Errors
- **Column not found**: Verify column name exists in table schema. Check for typos.
- **Table not found**: Table may have been renamed or dropped. Check available tables.
- **Syntax error**: Review SQL for missing commas, parentheses, or keywords.
- **Permission denied**: User may lack SELECT/INSERT/UPDATE permissions on the table.
- **Timeout**: Query exceeded 30-second limit. Add WHERE filters or LIMIT clause.

### API Call Errors
- **401 Unauthorized**: Check authentication header format and token validity.
- **403 Forbidden**: Insufficient permissions for the requested resource.
- **404 Not Found**: URL may be incorrect or resource deleted. Verify `$input.*` interpolation.
- **422 Unprocessable Entity**: Request body validation failed. Check JSON syntax and required fields.
- **500 Server Error**: External service issue. Suggest retry logic.
- **Connection timeout**: Increase timeout value or check network connectivity.
- **SSRF blocked**: URL resolves to a private IP address. Use public endpoints only.

### Custom Code Errors
- **NameError**: Variable not defined. Check `$input.*` references match upstream output.
- **KeyError**: Dictionary key doesn't exist. Use `.get('key', default)` instead.
- **TypeError**: Operation on incompatible types. Add type checking or conversion.
- **SyntaxError**: Python syntax issue. Review indentation, brackets, and colons.
- **Timeout exceeded**: Code ran longer than allowed (30s). Optimize algorithm or add early returns.

### Email Errors
- **Invalid recipient**: Email address format is invalid. Verify `$input.email` value.
- **SMTP connection failed**: Check system settings for SMTP configuration.
- **Message too large**: Body content exceeds server limits. Truncate or paginate.

### Condition Errors
- **Undefined key**: `data['field']` references a key that doesn't exist. Use `data.get('field')`.
- **Type mismatch**: Comparing incompatible types (e.g., string vs number). Add type conversion.
- **Syntax error**: Invalid Python expression. Review operators and parentheses.

### Webhook Errors
- **Connection refused**: Target URL is unreachable. Verify endpoint exists.
- **SSL certificate error**: Target server has invalid certificate. Check URL uses HTTPS.
- **Timeout**: Target server didn't respond in time. Increase timeout value.

## Diagnosis Approach
1. Identify the failing step type from the error context.
2. Match the error message pattern to known failures above.
3. Suggest specific fixes based on the step configuration.
4. Provide the corrected configuration as JSON when possible.

## Output Format
When diagnosing, return:
```json
{
  "explanation": "Plain English explanation of what went wrong",
  "suggested_fix": "Description of the fix",
  "fixed_config": { ... }  // Corrected step configuration if applicable
}
```

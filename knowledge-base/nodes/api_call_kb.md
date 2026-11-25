# API Call Node Knowledge Base

## Context
API call nodes (`api_call`) make HTTP requests to external services. They support GET, POST, PUT, DELETE, and PATCH methods with configurable headers and body.

## Generation Patterns

### GET Request
```json
{
  "method": "GET",
  "url": "https://api.example.com/users/$input.user_id",
  "headers": "{\"Authorization\": \"Bearer ${API_KEY}\", \"Content-Type\": \"application/json\"}",
  "body": ""
}
```

### POST Request
```json
{
  "method": "POST",
  "url": "https://api.example.com/orders",
  "headers": "{\"Authorization\": \"Bearer ${API_KEY}\", \"Content-Type\": \"application/json\"}",
  "body": "{\"customer_id\": \"$input.customer_id\", \"items\": $input.items_json}"
}
```

### PUT Request
```json
{
  "method": "PUT",
  "url": "https://api.example.com/orders/$input.order_id",
  "headers": "{\"Authorization\": \"Bearer ${API_KEY}\", \"Content-Type\": \"application/json\"}",
  "body": "{\"status\": \"shipped\", \"tracking_number\": \"$input.tracking\"}"
}
```

## Explanation Patterns
- Describe the HTTP method, target URL, authentication approach, and expected payload.
- Note any `$input.*` variable references in URL, headers, or body.

## Fix Patterns
- Common errors: 401 (bad auth), 403 (permission denied), 404 (wrong URL), 422 (invalid body), 500 (server error).
- Suggest checking header JSON syntax (must be valid JSON string).
- Suggest verifying URL interpolation with `$input.*` values.

## Safety Rules
- SSRF protection is enforced: private IPs (10.x, 172.16-31.x, 192.168.x, 127.x) are blocked.
- URLs must use HTTPS when possible.
- Never hardcode real API keys -- use `${VARIABLE_NAME}` placeholders.

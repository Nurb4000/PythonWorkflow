# Step Generation Prompts

## API Call Step
Generate an API call step with:
- HTTP method (GET, POST, PUT, DELETE, PATCH)
- URL endpoint
- Headers (authorization, content-type, etc.)
- Request body (for POST/PUT)
- Authentication configuration

Example prompt: "Create an API step to fetch user data from https://api.example.com/users/{id}"

## Database Query Step
Generate a database query step with:
- Query type (SELECT, INSERT, UPDATE, DELETE)
- Table name
- Columns
- Conditions/filters
- Parameters

Example prompt: "Query the users table for active accounts created after 2024-01-01"

## Email Step
Generate an email notification step with:
- Recipient(s)
- Subject line
- Body template
- Dynamic variables from workflow data

Example prompt: "Send an email to the user with their order confirmation details"

## Condition Step
Generate a conditional branch with:
- Expression using workflow variables
- Comparison operators
- Logical operators (AND, OR, NOT)

Example prompt: "Check if the order total is greater than $100 and the customer is premium"

## Form Step
Generate a form collection step with:
- Form fields (name, email, phone, etc.)
- Field types (text, email, number, select, checkbox)
- Validation rules
- Required fields

Example prompt: "Create a contact form with name, email, and message fields"

## Delay Step
Generate a delay/wait step with:
- Duration in seconds
- Optional: wait until specific time
- Optional: poll for condition

Example prompt: "Wait 5 minutes before sending the follow-up email"

## Webhook Step
Generate a webhook listener step with:
- Callback URL
- Expected payload structure
- Authentication tokens
- Retry configuration

Example prompt: "Listen for payment confirmation webhooks from Stripe"

## Custom Code Step
Generate custom Python code with:
- Input data access
- Output variables
- Error handling
- External library usage (if allowed)

Example prompt: "Transform the API response to extract user IDs and format dates"

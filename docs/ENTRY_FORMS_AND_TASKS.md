# Entry Forms & Form Tasks

## Entry Forms (Workflow Start Gate)

An entry form prompts users with a form before a workflow starts. The submitted data becomes the workflow's `input_data`, accessible to all downstream steps via `{{ input.field_name }}`.

### Setting Up an Entry Form

1. **Create a form** in the Form Designer (`/forms`)
   - Define fields (text, number, email, date, textarea, select, boolean)
   - Save and publish the form

2. **Assign to a workflow**
   - Go to the workflow's detail page (`/workflows/{id}`)
   - Scroll to **Portal Settings** section
   - Select a form from the **Entry Form** dropdown
   - Click **Save Entry Form**

3. **On the portal**, when a user clicks the workflow card:
   - The entry form modal appears with all defined fields
   - User fills out and submits the form
   - Workflow starts with the form data as `input_data`

### Data Flow

```
User submits entry form
    ↓
Form data → workflow.input_data
    ↓
Step 1 receives input_data as {{ input.* }}
    ↓
Step 2 receives Step 1 output as {{ steps.<step_id>.output }}
    ↓
...and so on
```

### Clearing an Entry Form

Select "None (start directly)" from the dropdown and save. The workflow will trigger immediately without prompting for data.

---

## Form Tasks (Mid-Workflow Human Steps)

A form task pauses workflow execution and creates a task assigned to a user or group. When the human opens the task, they see a form to fill out. Their submission becomes the step's output.

### Setting Up a Form Task

1. **Create a form** in the Form Designer with the fields you need

2. **Add a "form" step** in the Workflow Designer
   - Select step type: **Form**
   - Choose the form from the dropdown
   - Assign to a user or group
   - Connect outputs to downstream steps

3. **When the workflow reaches this step:**
   - A task is created and assigned
   - The assignee sees it in their Tasks dashboard
   - Opening the task displays the form
   - Submitting the form completes the task and continues the workflow

### Data Flow

```
Workflow runs → reaches Form step
    ↓
Task created, assigned to user/group
    ↓
Human opens task → sees form fields
    ↓
Human submits form → task completed
    ↓
Form data → step output → available as {{ steps.<step_id>.output }}
    ↓
Workflow continues to next step
```

---

## Key Differences

| Feature | Entry Form | Form Task |
|---------|-----------|-----------|
| **When** | Before workflow starts | Mid-workflow (as a step) |
| **Who fills it** | Workflow submitter | Assigned user/group |
| **Data becomes** | `input_data` (available to all steps) | Step output (available downstream) |
| **Creates a task** | No | Yes |
| **Pauses workflow** | No (workflow hasn't started) | Yes (waits for human response) |
| **Configured in** | Workflow Detail → Portal Settings | Workflow Designer → Form step |

---

## Field Types Supported

Both entry forms and form tasks support these field types:
- **Text** — short string input
- **Textarea** — long text input
- **Number / Integer** — numeric input
- **Email** — email-address validated input
- **Date / Date & Time** — date picker
- **Select (Dropdown)** — predefined options
- **Boolean (Checkbox)** — true/false toggle
- **URL** — web address input
- **Currency** — monetary value

---

## Reference Existing Fields

Form fields can be configured as "Reference Existing" to link to columns on other database tables. On submission, values save back to the referenced table. The target record ID is resolved from workflow context via `__ref_{field_name}` in submission data.

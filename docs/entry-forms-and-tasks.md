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
   - Select a form from the **Entry Form** dropdown (or "None (start directly)" to disable)
   - Click **Save Portal Settings** (this saves the entry form together with the portal settings)

3. **On the portal**, when a user clicks the workflow card:
   - The entry form modal appears with all defined fields
   - User fills out and submits the form
   - Workflow starts with the form data as `input_data`

> Note: The entry form selection is saved by the **Save Portal Settings** button. There is no separate save button.

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

Select "None (start directly)" from the dropdown and click **Save Portal Settings**. The workflow will trigger immediately without prompting for data.

---

## Form Tasks (Mid-Workflow Human Steps)

A form task pauses workflow execution and creates a task assigned to a user or group. When the human opens the task, they see a form to fill out. Their submission becomes the step's output.

### Setting Up a Form Task

1. **Create a form** in the Form Designer with the fields you need

2. **Add a "Human Task" or "Approval" step** in the Workflow Designer
   - Select step type: **Human Task** or **Approval**
   - Choose the form from the **Form** dropdown
   - Assign to a user or group (optional — unassigned tasks can be taken by anyone)
   - Connect outputs to downstream steps

   (A plain **Form** step runs automatically and reads the latest form submission; it does not create an assigned task.)

3. **When the workflow reaches this step:**
   - A task is created and assigned, and the workflow pauses
   - The assignee sees it in their Tasks dashboard and opens it (`/tasks/{id}`)
   - The task page renders the form, prefilled with any task data
   - Filling in the form and clicking **Complete Task & Save Data** submits the data, completes the task, and continues the workflow

> **Prefill from earlier steps:** Human task / approval forms are automatically pre-filled with any data accumulated earlier in the run (e.g. a user's entry-form submission, or the result of a previous form task). Only keys matching the form's own field names are copied, and metadata / intermediate step outputs are ignored. A per-step **Task Data (JSON)** block on the step still takes precedence over the automatic prefill. This makes the common "collect data up front, then review it in a later step" pattern work with zero configuration — just use a form with the same field names in both places.

### Working on a Form Task

- **Open** status — anyone with permission can click **Take Task** to claim ownership. The form is shown read-only until taken.
- **Owned** status — the owner can fill out the form and submit. The form data is saved as the task's result data.
- **Completed / Closed** status — the form is shown read-only with the saved data (for review).
- To **change** saved data, a reviewer can **Reject** the task (moving it back to open) and the assignee can re-take and re-submit.

### Data Flow

```
Workflow runs → reaches Human Task / Approval step
    ↓
Task created, assigned to user/group, workflow pauses
    ↓
Human opens task → sees form fields (prefilled from task_data)
    ↓
Human fills out + submits form → task completed
    ↓
Form data → task.result_data → step output.task_result
    ↓
Available downstream as {{ steps.<step_id>.output.task_result.<field> }}
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

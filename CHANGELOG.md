# Changelog

All notable changes to the Python Workflow System.

---

## [Unreleased] — 2026-08-09

### New Features

#### Workflow History Retention, Uploads Audit & Demo Seeding
- **Retain runs after workflow deletion** — `WorkflowRun.workflow_name` snapshots the workflow name at run creation; `workflow_runs.workflow_id` and `step_instances.step_id` are now nullable with `ON DELETE SET NULL`, so deleting a workflow keeps run history identifiable. Admin runs list joins the (now optional) workflow and falls back to the snapshot name.
- **Admin file-uploads audit + download access control** — `FormUpload` audit table records every upload (original name, stored name, content type, size, uploader); new `GET /admin/form-uploads` listing with `uploader_username`; downloads enforce role-based access (admin/developer always, uploader always, staff only when the file is referenced in their assigned tasks/runs); 25 MB upload cap.
- **Task-form prefill** — human-task forms are pre-filled from run input data (explicit step `task_data` wins); fixes a latent JSON-persistence bug in run input updates.
- **Seeded demo workflow** — startup seed (`app/services/demo_seed.py`) idempotently creates the "Demo: 4-Column Intake with Review" workflow (portal-visible, `environment="production"`, published), a 4-column entry form with Info Text labels, and a 2-column staff review form pre-filled from the entry. Fresh rebuilds get it automatically, like the marketplace demos.

**Backend files:**
| File | Purpose |
|------|---------|
| `backend/app/services/demo_seed.py` | Idempotent demo workflow + forms seeding |
| `backend/alembic/versions/d4e5f6a7b8c9_snapshot_workflow_name_on_runs_and_retain.py` | Nullable workflow/step FKs + run name snapshot |
| `backend/alembic/versions/e5f6a7b8c9d0_add_form_uploads_audit_table.py` | `form_uploads` audit table |
| `backend/tests/test_demo_seed.py`, `test_run_workflow_name_retention.py`, `test_form_uploads.py`, `test_task_form_prefill.py` | Feature tests |

**Frontend files:**
| File | Purpose |
|------|---------|
| `frontend/src/pages/UploadsAdmin.tsx` | Admin uploads listing page (`/admin/uploads`) |
| `frontend/src/pages/WorkflowRunsAdmin.tsx`, `RunMonitor.tsx`, `AdminDashboard.tsx` | Show snapshot workflow name; handle null workflow after deletion |

---

## [Unreleased] — 2026-08-06

### New Features

#### Internal Workflow & Node Marketplace (Phases 1-5)
In-app marketplace for publishing, discovering, and installing reusable workflow packages and node templates. Replaces the standalone demo-workflows area with a unified, DB-backed system.

- **Browse & Search** — `/marketplace` page with tabs (Workflows/Nodes/My Nodes), full-text search, category filter, tag cloud, sort, pagination
- **Publish Workflows** — "Publish to Marketplace" button on workflow detail page; exports workflow as JSON and creates marketplace listing with metadata form (name, description, category, tags, status)
- **Publish Nodes** — "Save to Marketplace" and "Save to My Nodes" buttons in the designer step editor; captures node config with title, description, category, tags
- **Install Workflows** — one-click install from marketplace; delegates to existing import service with configurable options (environment, conflict resolution, forms/groups/users); review-before-install security audit
- **Install Nodes** — returns step payload for direct designer insert AND saves copy to installer's My Nodes library
- **My Nodes Library** — personal collection of saved node templates; visible in marketplace tab and designer panel; click-to-insert into current workflow
- **Security Audit** — preview panel extracts step types, external URLs, custom code presence, SQL queries, email recipients, forms/groups references; two-step confirmation required before install
- **Downloads Counter** — increments on each successful install
- **Demo Migration** — 5 demo workflows seeded as marketplace items; old `/workflows/demo-list` and `/workflows/demo/{filename}` endpoints retired

**Backend files:**
| File | Purpose |
|------|---------|
| `backend/app/models/marketplace.py` | MarketplaceItem + SavedNodeTemplate ORM models |
| `backend/app/services/marketplace_service.py` | CRUD, search, install, audit, validation, secrets scan |
| `backend/app/api/marketplace.py` | REST router (`/marketplace`) |
| `backend/alembic/versions/c3d4e5f6a7b8_add_marketplace_tables.py` | Migration (both tables) |
| `scripts/seed_marketplace_demos.py` | Idempotent seed script for demo workflows |

**Frontend files:**
| File | Purpose |
|------|---------|
| `frontend/src/pages/Marketplace.tsx` | Browse, search, install, My Nodes, audit modal |
| `frontend/src/pages/WorkflowDetail.tsx` | "Publish to Marketplace" button + modal |
| `frontend/src/pages/WorkflowDesigner.tsx` | "Save to My Nodes", "⊕ Marketplace", My Nodes panel |
| `frontend/src/pages/WorkflowImportExport.tsx` | Demo section replaced with marketplace link |
| `frontend/src/services/api.ts` | `marketplaceApi` client |

**API Endpoints:**
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/marketplace/items` | Any authenticated | List items (filter: type, search, category, tag, sort, paginate) |
| GET | `/marketplace/items/{id}` | Any authenticated | Item detail with author name |
| POST | `/marketplace/items` | Admin/Dev | Publish workflow or node |
| PUT | `/marketplace/items/{id}` | Author/Admin | Update metadata/version |
| DELETE | `/marketplace/items/{id}` | Author/Admin | Delete or archive |
| POST | `/marketplace/items/{id}/install` | Admin/Dev | Install (workflow → import; node → payload + My Nodes) |
| GET | `/marketplace/items/{id}/package` | Admin/Dev | Raw package content download |
| POST | `/marketplace/items/{id}/preview` | Any authenticated | Security audit summary |
| GET | `/marketplace/my-nodes` | Admin/Dev | List personal node templates |
| POST | `/marketplace/my-nodes` | Admin/Dev | Save node to personal library |
| DELETE | `/marketplace/my-nodes/{id}` | Owner | Remove from personal library |
| GET | `/marketplace/categories` | Any authenticated | Category catalog + tag cloud |

**Removed endpoints:**
- `GET /workflows/demo-list` — replaced by marketplace browse
- `GET /workflows/demo/{filename}` — replaced by marketplace install

---

## [Unreleased] — 2026-08-03

### New Features

#### Universal Custom Fields Editor
Reusable component that renders custom fields dynamically on any admin/developer create/edit form. Eliminates the need for hardcoded form fields when database columns change.

- **CustomFieldsEditor** (`frontend/src/components/CustomFieldsEditor.tsx`) — shared React component
  - Props: `targetTable` (e.g., `"users"`), `existingData`, `onChange`, `disabled`
  - Fetches active custom field definitions for the given table via `dataFieldApi`
  - Renders appropriate input per field type: text, number, boolean, select, date, datetime, email, url, textarea
  - Returns a flat `{ field_key: value }` object that parents merge into `custom_data`
  - Returns `null` when no custom fields are defined for the table (zero UI overhead)

- **User Management** (`/admin/users`) — integrated CustomFieldsEditor on both create and edit forms
  - Create user: custom fields appear below role selector, submitted as JSON body with `custom_data` in params
  - Edit user modal: custom fields loaded from existing `user.custom_data`, saved back on update

- **Backend support**: `auth_service.create_user()` and `auth_service.update_user()` now accept `custom_data` dict
  - `POST /api/auth/register` — reads JSON body for custom_data, passes to create_user
  - `PUT /api/auth/users/{id}` — reads JSON body for custom_data, merges into existing record
  - `GET /api/auth/users` — returns `custom_data` in user list response

**How to add to other admin pages:** Drop `<CustomFieldsEditor targetTable="table_name" existingData={data} onChange={setHandler} />` into any create/edit form. The component handles fetching, rendering, and value changes automatically.

#### Workflow List Search, Filter & Sort
The workflow list page now supports client-side controls backed by server-side filtering and sorting for efficient navigation across many workflows.

- **Search** — text input filters workflows by name or description (case-insensitive ILIKE on the backend)
- **Status filter** — dropdown: All / Active / Inactive / Published / Draft
- **Sort** — choose field (Name, Created Date, Run Count, Step Count, Portal Order) and direction (Ascending/Descending)
- **Clear button** — resets search and status filters when either is active
- Filters reset automatically after creating or deleting a workflow

**Backend:** `GET /api/workflows/` now accepts optional query params: `search`, `status`, `sort_by`, `sort_order`

**Frontend files:** `frontend/src/pages/WorkflowList.tsx`, `frontend/src/services/api.ts`
**Backend file:** `backend/app/api/workflows.py`

#### Workflow Import/Export
Complete workflow portability between system instances for backup, development-to-production promotion, and demo/training distribution.

- **Export** — from workflow detail page: download as XML (human-readable) or JSON
  - Includes: workflow config, all steps with definitions, schedules, forms, groups, permissions
  - Symbolic refIds for all cross-references (step-to-step, form refs, group refs)
  - Excludes: runtime data, passwords, auto-generated IDs/timestamps

- **Import** — `/workflows/import` page with drag-and-drop file upload
  - Options: target environment (preserve/test/production), conflict handling (copy/skip/overwrite)
  - Toggle: create missing forms, create missing groups, match users by email
  - Result summary: what was created, matched, skipped, with warnings

- **Duplicate** — "⧉ Duplicate" button on workflow detail page creates an in-system copy

- **Demo Workflows** — 5 pre-built packages available from import page:
  - Hello World (API call → email)
  - Expense Approval (form → approval → branching → DB update)
  - Data Report (SQL query → report → scheduled email)
  - Form Collection (form → human review → conditional update)
  - Scheduled Cleanup (cron → query → condition → report → email)

**Backend files:**
| File | Purpose |
|------|---------|
| `backend/app/services/workflow_export_service.py` | Export to XML/JSON with ID remapping |
| `backend/app/services/workflow_import_service.py` | Import with conflict resolution + duplicate |
| `backend/app/api/workflow_import_export.py` | REST endpoints |
| `backend/app/data/demo-workflows/*.xml` | 5 demo workflow packages |

**Frontend files:**
| File | Purpose |
|------|---------|
| `frontend/src/pages/WorkflowImportExport.tsx` | Import page with drag-and-drop + options + demos |
| `frontend/src/pages/WorkflowDetail.tsx` | Export dropdown + duplicate button |
| `frontend/src/services/api.ts` | `workflowExportApi` client |

**API Endpoints:**
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/workflows/{id}/export?fmt=xml\|json` | Admin/Dev | Export workflow as downloadable file |
| POST | `/workflows/import-body` | Admin/Dev | Import workflow from body (large files) |
| POST | `/workflows/{id}/duplicate` | Admin/Dev | Duplicate workflow within system |
| GET | `/workflows/demo-list` | Authenticated | List available demo workflows |
| GET | `/workflows/demo/{filename}` | Authenticated | Download demo workflow file |

**Workflow list query params (GET /api/workflows/):**
| Param | Type | Description |
|-------|------|-------------|
| `search` | string | Case-insensitive filter on name and description |
| `status` | string | Filter: `active`, `inactive`, `published`, `draft` |
| `sort_by` | string | Sort field: `name`, `created_at`, `runs_count`, `steps_count`, `portal_order` (default: `name`) |
| `sort_order` | string | Sort direction: `asc`, `desc` (default: `asc`) |

#### SQL View Manager
Admins and developers can create named SQL views to simplify complex queries for report nodes and Data Explorer.

- **SQL Views page** (`/admin/views`, admin + developer) — full CRUD for database views
  - Create views with `CREATE VIEW ... AS SELECT ...` statements
  - Edit, activate/deactivate, delete (drops from database)
  - SQL preview panel to review definition before saving
  - Safety: only CREATE VIEW allowed, DML/DDL keywords blocked inside view definitions
- **Database sync**: all active views are recreated on application startup
- **Integration**: views appear as queryable tables in Data Explorer and can be referenced in report node SQL queries

**Backend files:**
| File | Purpose |
|------|---------|
| `backend/app/models/sql_views.py` | SQLView ORM model |
| `backend/app/services/sql_view_service.py` | View lifecycle management, validation, sync |
| `backend/app/api/sql_views.py` | CRUD API (`/sql-views/`) |

**Frontend files:**
| File | Purpose |
|------|---------|
| `frontend/src/pages/SQLViewManager.tsx` | SQL view CRUD UI with preview |
| `frontend/src/services/api.ts` | New API client: `sqlViewApi` |

#### SQL Query Support in Report Node
Report nodes can now execute raw SQL queries, not just display data from other steps.

- **Frontend** — new "SQL Query" option in report type dropdown
  - SQL textarea with monospace font for query editing
  - Row limit selector (1–10,000, default 100)
  - Helper text: `$input.field_name` references resolve from upstream step data
  - Node label shows "SQL Query" when that type is selected
- **Backend** — `ReportExecutor._execute_sql()` runs the query against the database
  - Safety: SELECT-only, rejects dangerous keywords (DROP, DELETE, UPDATE, INSERT, etc.)
  - Interpolation: `$input.field` values are substituted and properly escaped
  - Returns: columns, rows, row_count, executed_at (or error message on failure)
- **Workflow engine** — all executors now receive optional `db` session parameter for database access

**Files:** `frontend/src/pages/WorkflowDesigner.tsx`, `backend/app/services/step_executors.py`, `backend/app/services/workflow_engine.py`

#### Cross-Table Field References in Forms
FormDesigner fields can now reference existing database columns from any queryable table, with edit + save-back on submission.

- **FormField** — new properties: `source` (`'form'` or `'reference'`), `ref_table`, `ref_column`, `ref_record_id`
- **Field editor card** — dropdown to choose "New Field" vs "Reference Existing"
  - When referencing: table selector + column selector populated from `dataQueryApi.listTables()`
  - Reference fields have purple border for visual distinction
  - Required checkbox disabled for reference fields
- **Form preview** — reference fields render as editable inputs (not read-only)
- **Backend save-back** (`form_service.submit_form()`) — on submission, reference field values are written back to the source table row
  - Target record ID resolved from `__ref_{field_name}` in submission data (passed from workflow context)

#### Custom Field Extensions
Add dynamic fields to any table without schema migrations. Fields are stored as JSONB in a `custom_data` column on each extendable table.

- **Field Manager** (`/admin/fields`, admin only) — full CRUD for custom field definitions
  - 11 field types: string, text, number, boolean, date, datetime, select, email, url, currency, relationship
  - Scope: global (all records) or per-workflow
  - Select fields: configurable dropdown options
  - Relationship fields: link to another table with configurable target column and display column
  - Table schema reference panel shows existing native columns and custom fields to prevent naming conflicts
  - Conflict detection blocks creation of fields that duplicate native column names

- **Data Explorer** (`/admin/data`, admin + developer) — query any table visually or via raw SQL
  - Visual filter builder: pick table, add filter rows with column/operator/value, AND/OR logic, sort, pagination
  - SQL editor: free-form SELECT queries with safety guards (SELECT-only, 30s timeout, 10K row limit)
  - Relationship chain filters: query across FK joins (e.g., filter tasks by workflow name)
  - Custom field filters: filter on JSONB custom_data fields
  - CSV export: export current query results or full table dump

- **Audit trail**: all custom field CRUD and data changes logged to `audit_logs`

**Backend files:**
| File | Purpose |
|------|---------|
| `backend/app/models/custom_fields.py` | CustomFieldDefinition ORM model |
| `backend/app/services/data_query_service.py` | Query engine, relationship resolver, SQL executor, CSV export, audit logging |
| `backend/app/api/data_fields.py` | CRUD API for field definitions (`/data-fields/`) |
| `backend/app/api/data_query.py` | Visual query, SQL editor, inline/bulk custom data updates (`/data-query/`) |
| `backend/app/api/data_export.py` | CSV export endpoints (`/data-export/`) |
| `backend/alembic/versions/a1b2c3d4e5f6_add_custom_fields_and_data.py` | Migration: new table + `custom_data` JSONB on 6 existing tables |

**Frontend files:**
| File | Purpose |
|------|---------|
| `frontend/src/pages/FieldManager.tsx` | Custom field CRUD UI with schema reference panel |
| `frontend/src/pages/DataExplorer.tsx` | Visual query builder + SQL editor + CSV export |
| `frontend/src/services/api.ts` | New API clients: `dataFieldApi`, `dataQueryApi`, `dataExportApi` |

**Database changes:**
- New table: `custom_field_definitions` (13 columns)
- New column `custom_data JSON` added to: `tasks`, `workflow_runs`, `step_instances`, `users`, `groups`, `form_submissions`

---

### Bug Fixes

#### Form nav link doesn't exit edit mode (#3)
**Problem:** While editing a form, clicking "Forms" in the navbar did nothing — the URL was already `/forms` and React Router treated it as a no-op. The `showEditor` state remained `true`, trapping users on the edit view.

**Fix:**
- `showEditor` is now URL-driven via search params (`/forms?editing=1`) instead of local state
- Forms nav link uses explicit `navigate('/forms')` to clear search params when already on `/forms`
- `useEffect` resets editor state when `showEditor` transitions to `false`

**Files:** `frontend/src/pages/FormDesigner.tsx`, `frontend/src/App.tsx`

#### Cancel button stays disabled after save in Workflow Designer (#4)
**Problem:** The Cancel button was bound to `disabled={saving}`, which could leave it stuck after a save completed.

**Fix:** Button label now shows "Cancel" when there are unsaved changes, "Back" after saving. Removed `disabled` binding — the handler already confirms on unsaved changes.

**Files:** `frontend/src/pages/WorkflowDesigner.tsx`

#### New nodes appear off-screen in Workflow Designer (#5)
**Problem:** Adding a new step placed it at fixed coordinates far below the viewport with no auto-scroll.

**Fix:** After adding a step, `fitView({ padding: 1.5 })` is called via `requestAnimationFrame` to pan/zoom the canvas to include all nodes. Removed always-on `fitView` prop from ReactFlow to avoid resetting view on every render.

**Files:** `frontend/src/pages/WorkflowDesigner.tsx`

#### Admin menu mislabeled (#6)
**Problem:** The nav link said "Admin" but the page was just a reporting dashboard with no admin functions.

**Fix:** Renamed nav link to "Dashboard", page heading to "Dashboard", loading text to "Loading dashboard data...".

**Files:** `frontend/src/App.tsx`, `frontend/src/pages/AdminDashboard.tsx`

#### Forms cannot be unpublished (#8)
**Problem:** Forms could be published but had no way to revert back to draft status. Unlike workflows which have a toggle publish/unpublish button, forms only had a one-way "Publish" action.

**Fix:**
- Added `handleUnpublish` function that sets `is_published: false`
- Publish button now toggles: shows "Publish" (green) for drafts, "Unpublish" (orange) for published forms
- Behavior matches workflow publish/unpublish toggle

**Files:** `frontend/src/pages/FormDesigner.tsx`

#### Report node SQL query support (#9)
**Problem:** Report nodes could only display data from other workflow steps. No ability to run custom SQL queries directly.

**Fix:**
- Added "SQL Query" as a new report type option
- SQL textarea with `$input.field` interpolation for upstream data references
- Row limit control (1–10,000)
- Backend executes SELECT-only queries with safety guards against SQL injection
- Results returned as columns + rows for downstream steps

**Files:** `frontend/src/pages/WorkflowDesigner.tsx`, `backend/app/services/step_executors.py`, `backend/app/services/workflow_engine.py`

#### Workflow publish state not updating in list (#1)
**Problem:** Publishing/unpublishing a workflow on the detail page did not reflect in the workflow list. Two root causes:
1. `WorkflowList.tsx` had no Published column — only showed Active/Inactive status
2. Mutations in `WorkflowDetail.tsx` (`publishMutation`, `portalMutation`, `metadataMutation`, `versionMutation`) only invalidated their own detail cache, never the list cache

**Fix:**
- Added "Published" column to WorkflowList showing Published/Draft badge
- All mutations in WorkflowDetail now invalidate both `['workflow', workflowId]` AND `['workflows']`

**Files:** `frontend/src/pages/WorkflowList.tsx`, `frontend/src/pages/WorkflowDetail.tsx`

#### Session timeout during active work (#2)
**Problem:** JWT access token expired after 30 minutes with no refresh mechanism. On 401, the frontend did a hard redirect to `/login`, losing any unsaved work.

**Fix:**
- Token expiry increased from 30 min → **7 days** (10,080 min) in `config.py`
- Added proactive token refresh in `Auth.tsx`: decodes JWT `exp` claim, schedules a `/auth/me` ping 10 minutes before expiry
- Removed duplicate global axios interceptor that could fire twice on 401
- Excluded `/auth/me` from 401 redirect handler so proactive refresh doesn't accidentally log users out

**Files:** `backend/app/core/config.py`, `frontend/src/components/Auth.tsx`, `frontend/src/services/api.ts`

#### Workflow edit UI not visible
**Problem:** The "Edit Metadata" and version increment buttons on the workflow detail page were invisible — the header section was not wrapped in a `.card` container, so controls blended into the gray page background. Also, `.btn-warning` CSS class was missing entirely.

**Fix:**
- Wrapped header + stats grid in `<div className="card">` for proper white background and shadow
- Added `.btn-warning` CSS class (orange background)
- Updated `.stat-card` styling to work when nested inside a card

**Files:** `frontend/src/pages/WorkflowDetail.tsx`, `frontend/src/index.css`

#### SQLAlchemy mapper bug in auth model
**Problem:** Pre-existing bug — `User.groups` relationship had `back_populates="groups"` but the Group model's property is called `users`. This caused a mapper configuration error when the new custom_fields model was imported.

**Fix:** Changed to `back_populates="users"`.

**File:** `backend/app/models/auth.py`

---

### Usability Improvements

#### FormDesigner field editor labels (#7)
**Problem:** Field name and title inputs used only placeholder text. When a field had a default value like `field_1`, there was no way to tell if it was the name or title without clicking/clearing the input.

**Fix:** Added visible `<label>` elements ("Field Name", "Display Title", "Description") above each input in the field editor card. Placeholders remain as secondary hints.

**Files:** `frontend/src/pages/FormDesigner.tsx`

#### Human task assignment in Workflow Designer
**Problem:** User and group assignment on human_task/approval steps used raw `<input type="number">` fields requiring users to know numeric IDs by heart. React Flow nodes displayed `"Assigned to: 5"` instead of actual names.

**Fix:**
- Replaced number inputs with dropdown selects populated from `authApi.listUsers()` and `authApi.listGroups()`
- User dropdown shows `Full Name (email)` for each option
- Group dropdown shows group name with helper text explaining group-based task taking
- React Flow nodes now display resolved names: `"To: John Doe"` or `"To: Group: Finance"`
- Approval nodes show assignee + form name
- Form selector also stores `form_name` for node display

**Files:** `frontend/src/pages/WorkflowDesigner.tsx`, `backend/app/api/auth.py` (listUsers now accessible to developers, not just admins)

---

### API Changes

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/data-fields/` | GET | Admin/Dev | List custom field definitions (filterable by table, scope) |
| `/data-fields/` | POST | Admin/Dev | Create custom field definition |
| `/data-fields/{id}` | GET | Admin/Dev | Get single field definition |
| `/data-fields/{id}` | PUT | Admin/Dev | Update field definition |
| `/data-fields/{id}` | DELETE | Admin/Dev | Deactivate field (soft delete) |
| `/data-query/tables` | GET | Authenticated | List queryable tables with columns and custom fields |
| `/data-query/build` | POST | Admin/Dev | Execute visual filter builder query |
| `/data-query/sql` | POST | Admin/Dev | Execute raw SQL (SELECT-only, 30s timeout) |
| `/data-query/records/{table}/{id}/custom-data` | PUT | Admin/Dev | Update custom field on a single record |
| `/data-query/bulk-update/custom-data` | POST | Admin/Dev | Bulk update custom field on multiple records |
| `/data-export/table/{name}` | GET | Admin/Dev | Export full table to CSV |
| `/data-export/query` | POST | Admin/Dev | Export visual query results to CSV |
| `/auth/users` | GET | **Admin/Dev** (was admin-only) | List users — now includes `custom_data` in response |
| `/auth/register` | POST | Admin/Dev | Accepts JSON body for `custom_data` on user creation |
| `/auth/users/{id}` | PUT | Admin | Accepts JSON body for `custom_data`, merges into existing record |
| `/sql-views/` | GET | Admin/Dev | List all SQL views |
| `/sql-views/` | POST | Admin/Dev | Create new SQL view |
| `/sql-views/{id}` | PUT | Admin/Dev | Update SQL view definition |
| `/sql-views/{id}` | DELETE | Admin/Dev | Delete SQL view (drops from database) |

---

### Configuration Changes

| Setting | Old | New | File |
|---------|-----|-----|------|
| `access_token_expire_minutes` | `30` | `10080` (7 days) | `backend/app/core/config.py` |

---

## [Previous Versions]

See git history for earlier changes.

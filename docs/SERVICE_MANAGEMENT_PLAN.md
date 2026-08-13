# ITIL-Aligned Service Management Plan

## Progress

| Phase | Status | Completed Items |
|-------|--------|----------------|
| **Phase 1 — Services Foundation** | ✅ COMPLETE | 1.1 DB models, 1.2 migration, 1.3 API router, 1.4 workflow PATCH extension, 1.5 Admin ServiceManager page, 1.6 WorkflowDetail service selector, 1.7 Catalog page, 1.8 Service Detail view |
| **Phase 2 — Categories & Taxonomy** | ✅ COMPLETE | Category model + API implemented in Phase 1. 2.4 catalog grouping by category done in ServiceCatalog. |
| **Phase 3 — Priority Matrix & SLA** | ✅ COMPLETE | 3.1 Priority matrix API (system_settings), 3.2 SLA targets per service (custom_data editor in ServiceManager), 3.3 SLA display on Service Detail, 3.4 Priority selector on catalog submission, 3.5 workflow_runs priority + service_id columns with migration, 3.6 Priority Matrix admin settings page |
| **Phase 4 — Request Enhancements** | ✅ COMPLETE | 4.1 service_id on workflow_runs (done), 4.2 catalog vs offerings coexistence (already implemented), 4.3 related services cross-linking (done in ServiceCatalog). |
| **Phase 5 — SLA Monitoring** | ✅ COMPLETE | 5.1 SLA tracking columns on workflow_runs, 5.2 auto-populate targets at run creation, 5.3 response tracking on task take, 5.4 resolution tracking on run completion, 5.5 SLA stats API + admin dashboard widget, 5.6 breach notification scheduler (every 15min) |
| **Phase 6 — KB Integration** | ✅ COMPLETE | 6.1 KnowledgeBaseArticle model + migration, 6.2 KB CRUD API, 6.3 service_id linkage, 6.4 KB articles displayed on Service Detail, 6.5 "Helpful Articles" in catalog search, 6.6 KBArticleViewer page, 6.7 Admin KB manager tab in ServiceManager |
| **OLA — Task-Level Agreements** | ✅ COMPLETE | OLA tracking columns on tasks (priority, pickup/closure targets + met flags), auto-populate from group custom_data at task creation, pickup evaluation on task take, closure evaluation on complete/close, OLA stats API + admin dashboard widget, group OLA editor in UserManagement, OLA status badges + priority column on task dashboards |

### Session Log

- **2026-08-12**: Phase 1 complete. Created Service/Category models, Alembic migration, full CRUD API, Admin ServiceManager page with tabs, public ServiceCatalog with search/category filtering/detail view, and WorkflowDetail service selector. Committed in 7 incremental commits.
- **2026-08-12**: Phase 3 complete. Added priority matrix API (get/set in system_settings), portal priority matrix endpoint, SLA targets editor in ServiceManager form, priority selection modal on catalog workflow submission, workflow_runs priority + service_id columns with Alembic migration, and Priority Matrix admin settings page with editable levels/colors. Committed in 3 incremental commits.
- **2026-08-12**: Phase 5 complete. Added SLA tracking columns (sla_response_target_hours, sla_resolution_target_hours, sla_response_met, sla_resolution_met) to workflow_runs with migration. Auto-populate targets at run creation from service SLA config. Response SLA evaluated on first task take. Resolution SLA evaluated on run completion. SLA stats API endpoint and admin dashboard widget with compliance %, met/breached/pending breakdowns, top breach services. Breach notification scheduler runs every 15 minutes, marks breached runs, sends admin emails. Committed in 3 incremental commits.
- **2026-08-12**: Phase 6 complete. Created KnowledgeBaseArticle model with service_id FK and migration. Full CRUD API for KB articles (admin-only write, public read). Service detail endpoint returns linked KB articles. Catalog search surfaces "Helpful Articles" from KB matching the query. New KBArticleViewer page at /kb/:slug. Admin KB manager tab added to ServiceManager with create/edit/delete/publish controls. Committed in 2 incremental commits.
- **2026-08-12**: OLA (Operational Level Agreement) complete. Extends SLA concept to human tasks scoped by group rather than service. Added priority, ola_pickup_target_hours, ola_closure_target_hours, ola_pickup_met, ola_closure_met columns to tasks with migration. Auto-populate targets at task creation from assigned group's custom_data.ola_targets + run priority. Pickup OLA evaluated when task is taken (time from created→owned). Closure OLA evaluated on task complete/close (time from created→completed). OLA stats API (/services/ola-stats) and admin dashboard widget with compliance %, met/breached/pending breakdowns, top breach groups. Group OLA editor in UserManagement modal with per-priority pickup/closure hour inputs. OLA status badges + priority column on task dashboards. Committed in 3 incremental commits.

---

## Overview

Extend the workflow system with a **Services** layer so workflows can be organized under services, users can browse a service catalog, and admins get ITIL-aligned tooling — without locking into IT-only terminology. The concepts map to ITIL 4 but use generic names so HR, Finance, Operations, etc. can adopt them naturally.

---

## Phase 1 — Services Foundation (Core)

### 1.1 Database: `services` table

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `name` | String, unique | Display name (e.g. "Email Service", "Onboarding") |
| `key` | String, unique | Slug for references (e.g. `email_service`) |
| `description` | Text | Long-form description |
| `icon` | String | Emoji or short label for tile display |
| `category_id` | FK → `categories` (nullable) | See Phase 2 |
| `owner_id` | FK → `users` (nullable) | Service owner / accountable person |
| `support_group_id` | FK → `groups` (nullable) | Default group that handles requests for this service |
| `is_active` | Boolean | Soft-delete toggle |
| `sort_order` | Integer | Manual ordering in catalog |
| `custom_data` | JSONB | Extensible: SLA targets, cost center, etc. |
| `created_at` / `updated_at` | Timestamp | |

### 1.2 Database: Link workflows to services

Add `service_id` (nullable FK → `services`) to the existing `workflows` table via Alembic migration. A workflow with no service is "ungrouped" and still appears in Offerings as before.

### 1.3 Backend API — `/api/services/...`

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/services` | Any user | List services (users see active only; admin sees all) |
| GET | `/services/{id}` | Any user | Service detail with linked workflows |
| POST | `/services` | Admin | Create service |
| PUT | `/services/{id}` | Admin | Update service |
| DELETE | `/services/{id}` | Admin | Deactivate (soft-delete). Cascade: warn if workflows reference it |

### 1.4 Backend API — Workflow update

Extend the existing workflow PATCH endpoint to accept `service_id`. When a workflow is saved with a service, store the association.

### 1.5 Frontend — Admin: Service Manager page

Route: `/admin/services`

- Card grid of all services (active + inactive filter dropdown, like CI Types)
- Create / Edit form: name, key (auto-slugified), description, icon, owner (user picker), support group (group picker), sort order
- Deactivate / Reactivate buttons
- Shows count of linked workflows per service

### 1.6 Frontend — Workflow Designer: Service selector

In the workflow settings panel (where portal/offering settings live), add a **Service** dropdown so admins/developers can associate the workflow with a service. Default: unassigned.

### 1.7 Frontend — Service Catalog page

Route: `/catalog` (visible to all authenticated users)

- Search bar at top
- Category filter (Phase 2)
- Tile grid: each tile shows service icon, name, short description, and count of available workflows
- Clicking a tile opens the **Service Detail** view (see below)

### 1.8 Frontend — Service Detail view

When a user clicks a service tile:

1. **Header**: Service icon, name, description, owner, status badge
2. **Available Workflows**: Tile grid of published workflows linked to this service (same visual style as Offerings page). Each tile shows the workflow's portal icon, name, and "Submit" button to launch.
3. If no workflows are linked, show a message: *"No requests available for this service yet."*

---

## Phase 2 — Categories & Taxonomy

### 2.1 Database: `categories` table

Generic grouping layer above services.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `name` | String, unique | e.g. "IT Infrastructure", "People Operations", "Finance" |
| `key` | String, unique | Slug |
| `icon` | String | Emoji for catalog grouping |
| `description` | Text | |
| `sort_order` | Integer | |
| `is_active` | Boolean | |

### 2.2 Backend API — `/api/categories/...`

Standard CRUD (admin only). Categories are returned with service counts.

### 2.3 Frontend — Category Manager

Route: `/admin/categories` (or merged into Service Manager as a section)

- Simple list with create/edit/deactivate
- Drag-to-reorder for sort_order

### 2.4 Frontend — Catalog grouping

Service catalog groups tiles by category. Each category is a section header with its icon. Uncategorized services appear under "General".

---

## Phase 3 — Priority Matrix & SLA Framework

### 3.1 Generic Priority Model

Instead of ITIL-specific "Urgency × Impact", use a configurable priority matrix stored in system settings:

```json
{
  "priority_matrix": {
    "levels": [
      { "id": 1, "name": "Critical", "color": "#dc3545" },
      { "id": 2, "name": "High", "color": "#fd7e14" },
      { "id": 3, "name": "Medium", "color": "#ffc107" },
      { "id": 4, "name": "Low", "color": "#28a745" }
    ],
    "auto_calculate": true,
    "factors": ["urgency", "impact"]
  }
}
```

### 3.2 SLA Targets per Service

Store in `services.custom_data`:

```json
{
  "sla_targets": {
    "response_hours": { "1": 1, "2": 4, "3": 8, "4": 24 },
    "resolution_hours": { "1": 4, "2": 24, "3": 72, "4": 168 }
  }
}
```

Keyed by priority level ID. These are informational targets — not enforced automatically (that's Phase 5).

### 3.3 Frontend — SLA display

On the Service Detail page, show a small table:

| Priority | Response Target | Resolution Target |
|----------|----------------|-------------------|
| Critical | 1 hour | 4 hours |
| ... | ... | ... |

### 3.4 Frontend — Priority selector on workflow submission

When a user submits a workflow that belongs to a service with SLA targets, show a priority dropdown (or auto-set based on urgency/impact questions in the entry form).

---

## Phase 4 — Service Request Enhancements

### 4.1 Workflow run → Service request linkage

When a workflow run is triggered from the catalog (vs. the Offerings page), store `service_id` on the run record so all runs can be filtered by service later.

### 4.2 Catalog vs. Offerings distinction

- **Offerings** (`/offerings`): Flat list of all published workflows (current behavior, unchanged)
- **Catalog** (`/catalog`): Organized by services/categories; user drills into a service to see its workflows

Both coexist. The catalog is the ITIL-aligned entry point; offerings remains for quick access.

### 4.3 "Related Services" cross-linking

On a service detail page, show other services in the same category as clickable links for easy navigation.

---

## Phase 5 — SLA Monitoring (Stretch)

### 5.1 SLA tracking on workflow runs

Add columns to `workflow_runs`:
- `sla_response_target_hours` (int, nullable)
- `sla_resolution_target_hours` (int, nullable)
- `sla_response_met` (boolean, nullable)
- `sla_resolution_met` (boolean, nullable)

Populated at run start from the service's SLA config. Updated when the first task is picked up (response) and when the run completes (resolution).

### 5.2 Admin: SLA Dashboard widget

On `/admin` dashboard, add a card showing:
- % of runs meeting response SLA (last 30 days)
- % of runs meeting resolution SLA
- Top services by breach count

### 5.3 Breach notifications

Configurable email/notification when a run is approaching or has breached its SLA target. Could use the existing scheduler + email node pattern.

---

## Phase 6 — Knowledge Base Integration (Stretch)

### 6.1 Link KB articles to services

Add `service_id` (nullable) to the existing knowledge base table. When viewing a service detail page, show related KB articles as self-help resources above the workflow tiles.

### 6.2 "Did you mean?" suggestions

When a user searches the catalog, also search KB articles and surface relevant ones as "Helpful Articles" alongside matching services.

---

## Non-IT Adaptation Notes

| ITIL Concept | Generic Name Used | Rationale |
|-------------|-------------------|-----------|
| Service Catalog | **Catalog** | Works for HR services, finance requests, etc. |
| Service Request | **Workflow / Request** | Already the model |
| Service Owner | **Owner** | Accountability, not IT-specific |
| SLA | **Targets** | "Response/Resolution Targets" is generic |
| OLA (Operational Level Agreement) | **OLA / Internal Targets** | Pickup/Closure targets per group for human tasks |
| CI (Configuration Item) | **CI** | Already in CMDB; services can reference CIs |
| Incident | — | Out of scope; this system handles requests, not break-fix |
| Change Advisory Board | — | Out of scope; approval workflows already cover this |

---

## Implementation Order & Session Estimates

| Phase | Sessions | Key Deliverables |
|-------|----------|-----------------|
| 1 — Services Foundation | 2–3 | DB migration, API, admin page, catalog page, workflow association |
| 2 — Categories | 1 | Categories table, API, catalog grouping |
| 3 — Priority & SLA | 1–2 | Configurable matrix, SLA display on service detail |
| 4 — Request Enhancements | 1 | Catalog launch tracking, offerings coexistence |
| 5 — SLA Monitoring | 1–2 | Run-level tracking, dashboard widget |
| 6 — KB Integration | 1 | Service-KB linkage, search suggestions |

**Total estimated: 7–10 sessions**

---

## OLA (Operational Level Agreement) — Task-Level Tracking

Extends the SLA concept from services to internal team tasks. While SLAs are customer-facing (service → run), OLAs are internal (group → task).

| Concept | SLA (Service) | OLA (Task/Group) |
|---------|---------------|------------------|
| Scope | Workflow run | Human task within a run |
| Configured on | `services.custom_data.sla_targets` | `groups.custom_data.ola_targets` |
| Pickup metric | Response SLA (run started → first task taken) | Pickup OLA (task created → task taken) |
| Closure metric | Resolution SLA (run started → run completed) | Closure OLA (task created → task completed/closed) |
| Priority source | User selects on catalog submission | Inherited from workflow run priority |

OLA targets stored in group `custom_data`:

```json
{
  "ola_targets": {
    "pickup_hours": { "1": 0.5, "2": 2, "3": 4, "4": 8 },
    "closure_hours": { "1": 4, "2": 24, "3": 72, "4": 168 }
  }
}
```

---

## ✅ All Phases Complete

All 6 phases of the Service Management Plan have been implemented across 2 sessions. The system now supports:

- **Service catalog** with categories, search, and detail views
- **Priority matrix** with configurable levels and colors
- **SLA targets** per service with response/resolution tracking
- **SLA monitoring** with admin dashboard widget and breach notifications
- **Knowledge base articles** linked to services with search integration

---

## Files to Create / Modify

### New files
- `backend/app/models/services.py` — Service, Category models
- `backend/app/api/services.py` — Services + Categories API routes
- `frontend/src/pages/ServiceManager.tsx` — Admin service/category CRUD
- `frontend/src/pages/ServiceCatalog.tsx` — Public-facing catalog + detail view
- `backend/alembic/versions/xxxx_add_services.py` — Migration

### Modified files
- `backend/app/models/schemas.py` — Add `service_id` to Workflow
- `backend/app/api/workflows.py` — Accept `service_id` in create/update
- `backend/app/main.py` — Register new router
- `frontend/src/App.tsx` — Add routes + nav entry for Catalog
- `frontend/src/services/api.ts` — Add services API methods
- `frontend/src/pages/WorkflowDetail.tsx` — Service selector in settings

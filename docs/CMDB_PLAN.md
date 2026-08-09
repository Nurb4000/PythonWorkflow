# CMDB Feature Plan

## Overview

Add a Configuration Management Database (CMDB) to PythonWorkflow that allows:
- Defining CI (Configuration Item) types with custom field schemas
- Creating and managing CI records via UI forms
- Referencing CMDB data from workflow nodes (lookups, filters, enrichment)
- A new `cmdb_manager` role for non-admin users to manage CMDB data
- REST APIs for automation (bulk import, external feeds, integrations)

---

## Data Model Design

### `CIType` — Configuration Item Type (the "class")

Represents a category of assets: *Server*, *Network Device*, *Application*, *Database*, *Cloud Instance*, etc.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer, PK | |
| `name` | String(100), unique | Display name, e.g. "Server" |
| `key` | String(50), unique | Machine-readable slug, e.g. "server" |
| `description` | Text | Optional |
| `icon` | String(50) | Emoji or icon class for UI |
| `field_schema` | JSON | Array of field definitions (see below) |
| `is_active` | Boolean | Soft-disable support |
| `created_at` | DateTime | |
| `updated_at` | DateTime | |

**`field_schema` JSON structure** (mirrors existing form/CustomFieldDefinition patterns):
```json
[
  { "key": "hostname", "label": "Hostname", "type": "string", "required": true },
  { "key": "ip_address", "label": "IP Address", "type": "string", "required": false, "validation": "ipv4" },
  { "key": "cpu_cores", "label": "CPU Cores", "type": "number", "required": false },
  { "key": "os", "label": "Operating System", "type": "select", "options": ["Ubuntu", "RHEL", "Windows Server"] },
  { "key": "environment", "label": "Environment", "type": "select", "options": ["dev", "staging", "prod"] },
  { "key": "install_date", "label": "Install Date", "type": "date" },
  { "key": "notes", "label": "Notes", "type": "text" }
]
```

Supported field types: `string`, `text`, `number`, `boolean`, `date`, `datetime`, `select`, `email`, `url`, `relationship` (FK to another CI type).

### `ConfigurationItem` — Individual CI record

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer, PK | |
| `type_id` | Integer, FK → CIType.id | Which type this CI belongs to |
| `name` | String(255) | Human-readable name / title |
| `status` | String(30) | e.g. "active", "retired", "maintenance", "decommissioned" — or custom per-type |
| `ci_data` | JSON | Type-specific field values keyed by field `key` |
| `custom_data` | JSON | Existing pattern for CustomFieldDefinition extensions |
| `created_by` | Integer, FK → users.id | |
| `updated_by` | Integer, FK → users.id | |
| `created_at` | DateTime | |
| `updated_at` | DateTime | |

**`ci_data` example** (for a "Server" type):
```json
{
  "hostname": "web-prod-01",
  "ip_address": "10.0.1.50",
  "cpu_cores": 16,
  "os": "Ubuntu",
  "environment": "prod",
  "install_date": "2024-01-15",
  "notes": "Primary web server"
}
```

### `CIRelationship` — Links between CIs

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer, PK | |
| `source_ci_id` | Integer, FK → ConfigurationItem.id | |
| `target_ci_id` | Integer, FK → ConfigurationItem.id | |
| `relationship_type` | String(50) | e.g. "runs_on", "depends_on", "connected_to", "part_of" |
| `description` | Text | Optional context |
| `created_at` | DateTime | |

### `CIHistory` — Audit trail (optional, Phase 3+)

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer, PK | |
| `ci_id` | Integer, FK → ConfigurationItem.id | |
| `changed_by` | Integer, FK → users.id | |
| `changed_at` | DateTime | |
| `field_key` | String(100) | Which field changed (null = whole record) |
| `old_value` | JSON | |
| `new_value` | JSON | |

---

## New Role: `cmdb_manager`

### Backend Changes

**File**: `backend/app/api/auth.py`

Add dependency (following existing pattern):
```python
async def get_current_cmdb_manager(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("admin", "developer", "cmdb_manager"):
        raise HTTPException(status_code=403, detail="CMDB manager access required")
    return user
```

**File**: `backend/app/models/auth.py`

Update role column comment to include `cmdb_manager`:
```python
role = Column(String(20), nullable=False, default="user")  # admin, developer, cmdb_manager, staff, user
```

### Frontend Changes

**File**: `frontend/src/components/Auth.tsx`

Add to `roleDefaultPath`:
```typescript
case 'cmdb_manager': return '/cmdb'
```

**File**: `frontend/src/App.tsx`

Add `/cmdb` routes wrapped in `<RoleRoute roles={['admin', 'developer', 'cmdb_manager']}>`.

---

## Phase Breakdown

### Phase 1: Backend Core — Models, API, Migration
**Goal**: CMDB data layer is functional via API.

| # | Task | Files | Details |
|---|------|-------|---------|
| 1.1 | Create SQLAlchemy models | `backend/app/models/cmdb.py` | `CIType`, `ConfigurationItem`, `CIRelationship` (History deferred) |
| 1.2 | Re-export models | `backend/app/models/__init__.py` | Import cmdb models |
| 1.3 | Create Pydantic schemas | `backend/app/schemas/cmdb.py` | Create/Update/Response schemas for all 3 entities |
| 1.4 | Create API router | `backend/app/api/cmdb.py` | Full CRUD for CITypes, CIs, Relationships. Auth: admin/developer only initially. |
| 1.5 | Register router | `backend/app/main.py` | `app.include_router(cmdb_router, prefix="/cmdb", tags=["cmdb"])` |
| 1.6 | Alembic migration | `backend/alembic/versions/..._add_cmdb_tables.py` | Create 3 tables + indexes |
| 1.7 | Update alembic env | `backend/alembic/env.py` | Import cmdb models module |

**API Endpoints (Phase 1):**

CITypes:
- `GET    /cmdb/types` — List all CI types
- `POST   /cmdb/types` — Create CI type (admin only)
- `GET    /cmdb/types/{id}` — Get single type
- `PUT    /cmdb/types/{id}` — Update type (admin only)
- `DELETE /cmdb/types/{id}` — Soft-delete type (admin only)

Configuration Items:
- `GET    /cmdb/items` — List/filter CIs (`?type_id=N`, `?status=X`, `?field_key=value`)
- `POST   /cmdb/items` — Create CI
- `GET    /cmdb/items/{id}` — Get single CI (with type info)
- `PUT    /cmdb/items/{id}` — Update CI
- `DELETE /cmdb/items/{id}` — Delete CI
- `GET    /cmdb/items/{id}/relationships` — Get relationships for a CI

Relationships:
- `POST   /cmdb/relationships` — Create relationship
- `DELETE /cmdb/relationships/{id}` — Delete relationship

**Validation rules:**
- `field_schema` on CIType must have unique `key` values
- `ci_data` on CI must conform to its type's `field_schema` (required fields, type checks)
- Relationship cannot point to same CI (self-loop), cannot link deleted types
- `key` on CIType is auto-generated from `name` (slugified) if not provided

---

### Phase 2: New Role + Frontend Management UI
**Goal**: cmdb_manager role works; full CRUD UI for managing CMDB.

| # | Task | Files | Details |
|---|------|-------|---------|
| 2.1 | Add `cmdb_manager` role (backend) | `auth.py`, `models/auth.py` | New auth dep `get_current_cmdb_manager` |
| 2.2 | Wire role into frontend routing | `Auth.tsx`, `App.tsx` | Default path + nav entry + RoleRoute guards |
| 2.3 | Frontend API client | `frontend/src/services/api.ts` | `cmdbApi` object with all endpoint wrappers |
| 2.4 | CI Type Manager page | `frontend/src/pages/CITypeManager.tsx` | List/create/edit CI types; field schema editor (add/remove fields, set type/required/options) |
| 2.5 | CI List page | `frontend/src/pages/CItemList.tsx` | Table view with filters by type/status/fields; search; pagination |
| 2.6 | CI Detail/Edit form | `frontend/src/pages/CIDetail.tsx` | Dynamically rendered form from `field_schema`; shows relationships; edit inline |
| 2.7 | Relationship editor | Integrated into CIDetail | Add/remove relationships to other CIs; type selector dropdown |
| 2.8 | Nav sidebar entry | `App.tsx` | "CMDB" link visible to admin/developer/cmdb_manager |

**UI notes:**
- CI Type Manager is admin-only (structural changes)
- CI List/Detail is accessible to admin/developer/cmdb_manager
- Field schema editor reuses patterns from `FormDesigner.tsx` and `FieldManager.tsx`
- Dynamic form rendering can reuse `FormRenderer.tsx` with minor adaptation
- Use TanStack Query (`useQuery`, `useMutation`) following existing patterns

---

### Phase 3: Workflow Node Integration
**Goal**: Workflow steps can look up, filter, and reference CMDB data.

| # | Task | Files | Details |
|---|------|-------|---------|
| 3.1 | New step type: `cmdb_lookup` | `step_executors.py` | Looks up a CI by type + field criteria; returns CI data into `$input` |
| 3.2 | Register executor | `workflow_engine.py` | Add to `_register_default_executors()` |
| 3.3 | Frontend node type | `WorkflowDesigner.tsx` | Add `cmdbLookup` to `nodeTypes`, styling in `getNodeStyle()`/`nodeLabel()` |
| 3.4 | Step editor UI | `WorkflowDesigner.tsx` (inside `renderStepEditor`) | Form: select CI type → pick lookup fields → set match criteria → choose output field name |
| 3.5 | New step type: `cmdb_update` | `step_executors.py` | Updates an existing CI's fields by ID or lookup |
| 3.6 | Register + frontend for cmdb_update | Same pattern as 3.1-3.4 | |
| 3.7 | Condition step: CMDB filter | `WorkflowDesigner.tsx` | In condition editor, allow referencing CMDB types as data sources (like database_query visual builder) |
| 3.8 | Human task: CMDB assignment | `WorkflowDesigner.tsx` | When assigning tasks, allow filtering users/groups by CMDB attributes (e.g., "assign to owner of this server") |

**`cmdb_lookup` step definition example:**
```json
{
  "ci_type_id": 1,
  "lookup_fields": [
    { "field_key": "hostname", "operator": "=", "value": "$input.server_name" }
  ],
  "output_var": "server_ci"
}
```
Result: `$input.server_ci` contains the full CI record.

**`cmdb_update` step definition example:**
```json
{
  "ci_id": "$input.server_ci.id",
  "updates": {
    "status": "maintenance",
    "notes": "Under maintenance since $input.maintenance_start"
  }
}
```

---

### Phase 4: Automation APIs
**Goal**: External systems can feed CMDB data programmatically.

| # | Task | Files | Details |
|---|------|-------|---------|
| 4.1 | Bulk import endpoint | `backend/app/api/cmdb.py` | `POST /cmdb/items/bulk-import` — Accepts array of CI records; upsert by type+key field; returns summary |
| 4.2 | Bulk import validation | Same | Dry-run mode (`?dry_run=true`) returns validation errors without writing |
| 4.3 | API token scoping | `backend/app/api/auth.py` | Allow API tokens to be scoped to "cmdb_read" / "cmdb_write" permissions |
| 4.4 | Export endpoint | `backend/app/api/cmdb.py` | `GET /cmdb/items/export?format=json\|csv&type_id=N` — Export CIs for backup/sync |
| 4.5 | Webhook trigger: CI events | `backend/app/api/cmdb.py` + `webhooks.py` | When a CI is created/updated/deleted, optionally fire a configured workflow (like form submission triggers) |
| 4.6 | Search API | `backend/app/api/cmdb.py` | `GET /cmdb/search?q=term&type_id=N` — Full-text search across CI names and ci_data values |
| 4.7 | Relationship graph API | `backend/app/api/cmdb.py` | `GET /cmdb/items/{id}/graph?depth=2` — Returns adjacency for impact analysis |

**Bulk import format:**
```json
{
  "type_key": "server",
  "records": [
    { "name": "web-01", "ci_data": { "hostname": "web-01", "ip_address": "10.0.1.50", ... } },
    { "name": "web-02", "ci_data": { "hostname": "web-02", "ip_address": "10.0.1.51", ... } }
  ],
  "upsert_key": "hostname"
}
```

---

### Phase 5: Polish + History Tracking (Optional)
**Goal**: Audit trail, advanced features.

| # | Task | Files | Details |
|---|------|-------|---------|
| 5.1 | CIHistory model + migration | `models/cmdb.py`, alembic | Track field-level changes |
| 5.2 | History API | `api/cmdb.py` | `GET /cmdb/items/{id}/history` |
| 5.3 | History UI | `CIDetail.tsx` | Timeline view of changes |
| 5.4 | CI type templates | `models/cmdb.py` + UI | Pre-built type definitions (Server, Switch, App, DB) for quick start |
| 5.5 | Dashboard widgets | New page or AdminDashboard | CI counts by type/status, recent changes |
| 5.6 | Permission refinement | `api/cmdb.py` | Per-type or per-CI ownership/scoping (future: restrict cmdb_managers to subsets) |

---

## Session Execution Order

Recommended order for implementing across sessions (respects token limits):

1. **Session 1**: Phase 1 — Backend core (models, schemas, API, migration). Largest single chunk but well-defined.
2. **Session 2**: Phase 2 tasks 2.1–2.4 — Role + CI Type Manager page.
3. **Session 3**: Phase 2 tasks 2.5–2.8 — CI List/Detail pages + nav integration.
4. **Session 4**: Phase 3 — Workflow node integration (cmdb_lookup, cmdb_update executors + frontend).
5. **Session 5**: Phase 4 — Automation APIs (bulk import, export, search, graph).
6. **Session 6**: Phase 5 — Polish (optional, as needed).

---

## Design Decisions & Rationale

1. **JSON-based `ci_data` over EAV model**: Follows existing patterns (`WorkflowStep.definition`, `User.custom_data`). Simpler queries, no N+1 joins, flexible per-type schemas. Trade-off: harder to index individual fields (mitigated by targeted search API in Phase 4).

2. **`field_schema` on CIType**: Self-describing types. The frontend can render dynamic forms without hardcoded field lists. Mirrors how `FormDesigner` works.

3. **`cmdb_manager` role vs group-based permissions**: Simpler to implement (follows existing role pattern). Can add per-type/per-CI scoping later if needed.

4. **CIType editing is admin-only**: Structural changes (adding/removing fields) affect all CIs of that type. cmdb_managers can create/edit/delete CI *records* but not modify type definitions.

5. **Relationships as separate table**: Keeps the graph explicit and queryable. Supports impact analysis ("what depends on this server?"). Deferred to Phase 1 but UI in Phase 2.

6. **Workflow integration via dedicated step types** (`cmdb_lookup`, `cmdb_update`): Cleaner than trying to shoehorn into `database_query`. Provides type-safe field references and better UX in the designer.

---

## Open Questions

- Should CI types support inheritance? (e.g., "Linux Server" extends "Server") — Deferred, not in initial scope.
- Do we need soft-delete on CIs? Currently planning hard delete. Can add if audit requirements demand it.
- Should the CMDB have its own permission model separate from user roles? (e.g., "this cmdb_manager can only edit 'server' type") — Phase 5 territory.

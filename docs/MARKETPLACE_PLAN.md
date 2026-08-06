# Internal Workflow & Node Marketplace — Implementation Plan

**Status:** Phase 2 complete — install, audit preview, my-nodes (backend)
**Date:** 2026-08-05
**Author:** opencode
**Last Updated:** 2026-08-06 — Phase 2 implemented and tested (45/45 green)

## Goal

Give developers an in-app place to **publish, discover, and install** two kinds of reusable
artifacts so nobody rebuilds the same workflow or node twice:

1. **Workflow packages** — full workflows with dependencies (steps, forms, groups, schedules,
   permissions), reusing the export/import format we already shipped in Phase 9.
2. **Node templates** — a single configured step (e.g. "Send SMTP digest with attachment",
   "Get user by email", "Scheduled cleanup trigger") that can be inserted straight into the
   designer.

Both artifacts are stored in one "Marketplace", browsed/searchable, and installed with
one click through the existing import pipeline.

**Phases 1 and 2 implemented.** Backend foundation + install/audit/my-nodes complete.
Remaining: Phase 3 (frontend browse), Phase 4 (publish UX + designer integration), Phase 5 (seed demos, hardening).

---

## Decisions For Review

| # | Decision | Recommendation | Open question? |
|---|----------|----------------|----------------|
| D1 | Storage | DB-backed (`marketplace_items` table + alembic migration). Content stored as TEXT (serialized package / node JSON). | — |
| D2 | Who can publish/install/edit | **Confirmed:** Admin + Developer can publish and use. Archive/delete any item: Admin only. Browse: all authenticated users. | — |
| D3 | v1 social features | **Confirmed:** downloads counter only. No star ratings, comments, screenshots, or version diffs. | — |
| D4 | Workflow install path | Server-side `POST /marketplace/items/{id}/install` that delegates to existing `workflow_import_service.import_workflow()` and returns the existing `ImportResult`. | — |
| D5 | Node install path | **Confirmed:** installing a node does both — (a) returns the step payload for direct insert into the currently-open designer graph, and (b) saves a copy to the user's personal "My Nodes" library. | — |
| D6 | Existing 5 demos | **Confirmed:** migrate the demos into the marketplace as published items. Retire the separate demo area — remove `/workflows/demo-*` endpoints and the "Demo & Training Workflows" section on the import page. One area only. | — |
| D7 | Install trust | "Review before install" audit (step types, external URLs, custom_code, SQL, forms/groups) shown in UI before import runs. Publish-time validation + secrets warning. | — |

---

## Alternatives Considered

1. **Git repo of packages** — simple, zero code, but no browse/search/install UX, no ratings,
   no "insert node into designer", and requires manual file shuffling. Discarded.
2. **Extend the filesystem `demo-workflows/` dir** — current state works, but no metadata,
   discovery, versioning, or author attribution, and it's a dev-code change to add each item.
3. **DB-backed in-app marketplace** ✅ — one table + thin service on top of the already-working
   export/import services. Smallest delta with the biggest payoff.

The key insight: **import/export already solves the hard 90%** (ID remapping, conflict
resolution, form/group/user matching). The marketplace is a thin, metadata-driven wrapper.

---

## What We Already Have (Reuse Map)

| Asset | Location | Reused for |
|-------|----------|------------|
| Export service (`export_workflow`) | `backend/app/services/workflow_export_service.py` | Generate package content on "Publish workflow" |
| Import service (`import_workflow`, `ImportResult`) | `backend/app/services/workflow_import_service.py` | Install workflow items |
| Demo endpoints pattern | `backend/app/api/workflow_import_export.py:168-210` | Serve package content / seed items |
| Import page + result rendering | `frontend/src/pages/WorkflowImportExport.tsx` | Model for install UI + result summary |
| Workflow list search/filter/sort | `backend/app/api/workflows.py`, `frontend/src/pages/WorkflowList.tsx` | Marketplace list params/UI pattern |
| Node validation (`VALID_STEP_TYPES`) | `backend/app/services/ai_service.py:17-30` | Validate published node items |
| Step template concept (P5.4) | `backend/app/services/template_service.py:46-63` | Superseded/extended by node items |
| Export/Duplicate buttons | `frontend/src/pages/WorkflowDetail.tsx` | Anchor "Publish to Marketplace" |
| Step config editors | `frontend/src/pages/WorkflowDesigner.tsx` | "Save node to Marketplace" + insert-node |
| Alembic migrations | `backend/alembic/versions/` | New table |
| Router registration | `backend/app/main.py:32-48` | Mount `/marketplace` |

---

## Data Model

New table `marketplace_items` (alembic migration, one file):

```
marketplace_items
  id               Integer PK
  item_type        String(20)   # 'workflow' | 'node'
  name             String(255)  (indexed)
  description      Text
  category         String(100)  # from a controlled catalog, see below
  tags             JSON         # list[str], free-form
  author_id        Integer FK users.id
  version          Integer default 1
  content          Text         # workflow: serialized WorkflowPackage (XML/JSON);
                                # node: JSON string of step payload (see shape below)
  content_format   String(10)   # 'xml' | 'json'
  node_type        String(50)   # null for workflows; step_type for nodes (e.g. 'api_call')
  status           String(20)   # 'draft' | 'published' | 'archived'
  is_active        Boolean default True
  downloads_count  Integer default 0
  created_at       DateTime
  updated_at       DateTime
```

Second new table `saved_node_templates` (personal "My Nodes" library, D5):

```
saved_node_templates
  id                        Integer PK
  user_id                   Integer FK users.id (indexed)
  step_type                 String(50)
  title                     String(255)
  description               Text
  definition                JSON
  condition_expr            Text
  is_enabled                Boolean default True
  max_retries               Integer default 0
  retry_delay_seconds       Integer default 0
  failure_hook_url          String(500)
  source_marketplace_item_id Integer FK marketplace_items.id (nullable)
  created_at                DateTime
```

**Node item `content` payload** (JSON) — mirrors `WorkflowStep` so the designer can consume it directly:

```json
{
  "step_type": "api_call",
  "title": "Fetch Posts",
  "description": "GET from JSONPlaceholder",
  "definition": { "method": "GET", "url": "...", "headers": {}, "next_step_ids": [] },
  "condition_expr": "",
  "is_enabled": true,
  "max_retries": 0,
  "retry_delay_seconds": 0,
  "failure_hook_url": ""
}
```

**Workflow item `content`** = the exact output of `workflow_export_service.export_workflow()`.

**Categories (v1 catalog):** `Data / ETL`, `Notifications`, `Approvals & Tasks`, `Reporting`,
`Integrations`, `Schedules & Maintenance`, `Onboarding`, `General`. Free-form `tags` on top.

---

## API Surface (router `marketplace`, prefix `/marketplace`)

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | `/marketplace/items` | Any authenticated | List. Params: `item_type`, `search`, `category`, `tag`, `status`, `sort_by` (`downloads`/`name`/`updated_at`), `sort_order`, `page`, `page_size` |
| GET | `/marketplace/items/{id}` | Any authenticated | Detail incl. author name + preview metadata |
| POST | `/marketplace/items` | Admin/Dev | Publish (workflow or node). Validates content. |
| PUT | `/marketplace/items/{id}` | Author or Admin | Update metadata / new version |
| DELETE | `/marketplace/items/{id}` | Author or Admin (Admin can archive any) | Delete or archive |
| POST | `/marketplace/items/{id}/install` | Admin/Dev | Install (bumps `downloads_count`). Workflow → import via existing service; node → returns step payload **and** saves a copy to the installer's My Nodes library (D5). |
| GET | `/marketplace/items/{id}/package` | Admin/Dev | Raw package content (supports manual download/drag into import page) |
| POST | `/marketplace/items/{id}/preview` | Any authenticated | Audit summary (steps, URLs, custom_code, SQL, forms/groups) for "review before install" |
| GET | `/marketplace/my-nodes` | Admin/Dev | List the user's personal node templates |
| POST | `/marketplace/my-nodes` | Admin/Dev | Save a node from the designer to the user's library |
| DELETE | `/marketplace/my-nodes/{id}` | Owner | Remove from personal library |
| GET | `/marketplace/categories` | Any authenticated | Category catalog + tag cloud |

New backend files:
- `backend/app/models/marketplace.py` — `MarketplaceItem` + `SavedNodeTemplate` models
- `backend/app/services/marketplace_service.py` — CRUD, validation, audit, install, my-nodes
- `backend/app/api/marketplace.py` — router
- `backend/alembic/versions/xxxx_add_marketplace_items.py` — migration (both tables)

---

## Security & Trust

Installed workflows can execute `custom_code` (sandboxed), make API/webhook calls, and run SQL.
Mitigations baked into the plan:

1. **Review-before-install** — `POST /preview` extracts and displays: step types used, external
   URLs, custom_code presence, SQL statements, forms/groups referenced, email recipients. The
   UI requires a conscious "I reviewed this, import it" click.
2. **Publish-time validation** — workflow items are parsed with the import parser (dry-run, no
   DB writes); node items validated against `VALID_STEP_TYPES` required fields and the known
   step-type list. Invalid content is rejected at publish, not at install.
3. **Secrets warning** — on publish, scan step definitions for obvious secrets
   (`sk-`, `Bearer `, `api_key=`, `password=`, `secret`). Publish is **blocked** for workflow
   packages; node items warn but allow (single node is easier to eyeball). Mirrors the export
   service's existing "excludes passwords" rule.
4. **Trust boundary note** — this is an internal marketplace. Installed workflows still respect
   all existing executor sandboxes (SSRF block, eval boundaries, read-only SQL checks). No new
   execution paths are added.

---

## Phased Implementation (one phase ≈ one session)

Legend: `[ ]` pending · `[~]` in progress · `[x]` done

### Phase 1 — Backend foundation: schema, model, service, core API **[COMPLETE]**
- [x] Alembic migration creating `marketplace_items` + `saved_node_templates` (`c3d4e5f6a7b8_add_marketplace_tables.py`)
- [x] `MarketplaceItem` + `SavedNodeTemplate` models in `backend/app/models/marketplace.py`
- [x] `marketplace_service.py`: create/get/list/update/delete/archive; list search/filter/sort/pagination (mirroring workflows.py)
- [x] `backend/app/api/marketplace.py` with the read + CRUD endpoints above
- [x] Register router in `backend/app/main.py`
- [x] Tests: 31 tests — model round-trip, list filters/sort/pagination, CRUD authz (author vs admin), publish validation, secrets blocking/warning, categories/tags
- **Exit:** `pytest` green (31/31 marketplace tests pass; 3 pre-existing template-service failures unrelated)

**Notes:**
- Used `Text` columns with manual JSON serialization for `tags` and `definition` for cross-database compatibility (SQLite + PostgreSQL).
- Router registered at `/marketplace` prefix.
- Auth: `get_current_user` for browse, `get_current_developer` for CRUD/my-nodes.
- Secrets scan blocks workflow publish, warns on node publish (per plan D7).

### Phase 2 — Publish/install/audit/my-nodes (backend) **[COMPLETE]**
- [x] `POST /items/{id}/install` for workflows → `workflow_import_service.import_workflow()`, return `ImportResult`, bump `downloads_count`
- [x] `POST /items/{id}/install` for nodes → returns step payload **and** saves a copy to the installer's `saved_node_templates` (D5)
- [x] `POST /items/{id}/preview` audit extractor (steps, URLs, custom_code, SQL, forms/groups)
- [x] Node item validation on publish (`VALID_STEP_TYPES`, allowed step types) — implemented in Phase 1
- [x] Secrets scan on publish + block/warn logic — implemented in Phase 1
- [x] My Nodes endpoints: `GET /my-nodes`, `POST /my-nodes`, `DELETE /my-nodes/{id}`; `GET /categories` — implemented in Phase 1
- [x] Tests: install end-to-end (package → workflow row created), node install (payload returned + library row created), preview extraction, secrets rejection, my-nodes ownership
- **Exit:** `pytest` green (45/45 — 31 Phase 1 + 14 Phase 2)

**Notes:**
- Install endpoint accepts query params: `on_conflict`, `environment`, `create_forms`, `create_groups`, `match_users_by_email`.
- Workflow install delegates to `workflow_import_service.import_workflow()` and bumps `downloads_count` on success.
- Node install returns both the raw step payload (for designer insert) and a saved copy in user's My Nodes library with `source_marketplace_item_id` linkage.
- Preview/audit extracts: step types, external URLs (recursive), custom_code presence, SQL queries, email recipients, forms/groups references. Works for both JSON and XML workflow packages.
- Audit warns on custom code and database query presence for review-before-install UX.

### Phase 3 — Marketplace frontend (browse)
- [ ] `frontend/src/services/api.ts` — `marketplaceApi` client (items + my-nodes)
- [ ] `frontend/src/pages/Marketplace.tsx` — tabs (Workflows/Nodes), search, category/tag filter, sort, card grid, item detail modal with audit + Install button
- [ ] Route `/marketplace` + nav link in `App.tsx` (admin/developer)
- [ ] Install workflow flow: call install endpoint, render existing `ImportResult` summary (mirrors `WorkflowImportExport.tsx`)
- [ ] "My Nodes" library page/panel (list, delete saved nodes)
- **Exit:** browse + install a seeded/demo item works end-to-end in UI

### Phase 4 — Publish UX + designer integration
- [ ] "Publish to Marketplace" on `WorkflowDetail.tsx` (next to Export/Duplicate): generates package via export service, opens metadata form (name/description/category/tags/status)
- [ ] "Save to Marketplace" in the node editor (`WorkflowDesigner.tsx` step config panel)
- [ ] "Save to My Nodes" in the node editor (reuses `POST /marketplace/my-nodes`)
- [ ] "Install node" flow in designer: insert returned step payload into the current graph (D5 direct-insert)
- [ ] "My Nodes" library panel in the designer: drag a saved node into the current workflow (D5 library)
- [ ] Manual "New Marketplace Item" form (authoring directly, incl. node payload builder)
- **Exit:** publish from a workflow and from a node, install a node into the designer (both paths), all via UI

### Phase 5 — Seed demos, hardening, docs
- [ ] Seed the 5 `demo-workflows/*.xml` files as published marketplace items (idempotent seed script or migration)
- [ ] Retire `/workflows/demo-list` + `/workflows/demo/{filename}` endpoints and the "Demo & Training Workflows" section in `WorkflowImportExport.tsx` (marketplace is now the single home for demos)
- [ ] Delete `backend/app/data/demo-workflows/` directory (source of truth moves to the DB)
- [ ] Security pass: review validation edge cases, import path reuse, audit display accuracy
- [ ] Update `README.md`, `DESIGN.md`, `CHANGELOG.md`
- [ ] Full backend `pytest` + frontend build/smoke
- **Exit:** complete feature, docs updated, tree green

---

## Backward Compatibility & Rollback

- **Backward compatible:** the import/export endpoints are untouched. The marketplace only
  *adds* a `/marketplace` router and two tables.
- **Intentionally removed (D6):** `/workflows/demo-list` + `/workflows/demo/{filename}` and the
  import page's demo section are retired — the marketplace replaces them as the single home for
  demo/training workflows.
- **Install path reuse:** marketplace install calls the same import service as the import page,
  so conflict resolution and ID remapping behave identically.
- **Rollback per phase:** Phase 1–2 (backend) are revertible by dropping the router registration
  and migration; no existing data is mutated. Phase 3–4 (frontend) are additive routes/components.
  Nothing is rewritten in place.

---

## Explicitly Out Of Scope (v1)

- Comments/discussion threads, screenshots, preview images
- Star ratings / reviews (v1 = downloads counter only, per D3)
- Version history / diffing between versions
- Multiple environments/instances, external/remote registries, cross-org sharing
- Full admin moderation UI (archive/delete only for v1)
- Automated "install as dependency" chains (installing workflow A that references workflow B)

---

## Testing Checklist

- [ ] Publish a workflow from the detail page → appears in marketplace list
- [ ] Publish a node from the designer → appears under the Nodes tab
- [ ] Search/filter/sort/pagination on `/marketplace/items`
- [ ] Install a workflow → creates workflow (+ forms/groups/schedules) and returns ImportResult
- [ ] Install with name conflict → copy/skip/overwrite behave as on the import page
- [ ] Install a node from the marketplace → step payload returned and inserted into the designer graph, and a copy saved to My Nodes (D5)
- [ ] Save a node to My Nodes from the designer → appears in library; deletable by owner only
- [ ] Preview audit shows correct step types, URLs, custom_code, SQL, forms/groups
- [ ] Invalid node content rejected at publish; obvious secrets blocked/warned
- [ ] Downloads counter increments on each install
- [ ] Demo workflows are browsable/installable from the marketplace (single area, demo endpoints removed)
- [ ] Full backend `pytest` + frontend build pass

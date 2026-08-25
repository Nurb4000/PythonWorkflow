# CMDB_GAPS

Verified inventory of CMDB missing/incomplete pieces so items can be picked
off one at a time. Created 2026-08-24 after code recon (previous session's
CMDB task list was never written down). Status: `[ ]` open, `[x]` done.

## Built but invisible: backend + API client exist, NO UI anywhere

These work end-to-end at the API level and are simply never rendered:

- [x] **CI Relationships UI**: typed source/target links between CIs.
      Backend: `POST/DELETE /cmdb/relationships`, `GET /cmdb/items/{id}/relationships`
      (`models/cmdb.py::CIRelationship`). Client: `cmdbApi.createRelationship`,
      `.deleteRelationship`, `.getItemRelationships`. 
      ~~DONE 2026-08-25 (commit `a5128da`): `/cmdb/items/:id/relationships` page with
      create form (type selector, target ID, properties JSON) and delete. Link from
      CI detail view.~~
- [x] **CI dependency graph**: interactive graph of a CI's relationship
      neighborhood. Backend: `GET /cmdb/items/{id}/graph?depth=` 
      (`get_ci_graph`). Client: `cmdbApi.getItemGraph`. 
      ~~DONE 2026-08-25 (commit `fbd0853`): React Flow viewer at `/cmdb/items/:id/graph`.
      Component `CIDependencyGraph.tsx` fetches graph and renders nodes/edges.~~
- [ ] **Bulk import UI**: CSV/JSON bulk creation of CIs. Backend:
      `POST /cmdb/items/bulk-import`. Client: `cmdbApi.bulkImport`. Needed:
      upload/paste UI per type with row-level error reporting.
- [ ] **Type webhooks admin**: per-CI-type webhook configuration exists only
      as backend endpoints (`configure_type_webhook`, `get_type_webhook`) —
      not even bound in `services/api.ts`. Decide whether to expose or cut.
- [ ] **CSV export wiring**: `export_cis` backend endpoint exists; confirm
      whether any UI path reaches it (suspected orphan).

## Done recently

- [x] CI type read-only View mode; lists hidden behind type/item forms;
      cold-load crash fix (commit `594d415`, 2026-08-24).

## Deliberately deferred to SCALE_GOVERNANCE_PLAN

Cross-referenced so this file stays the single checklist for CMDB-specific
work; do not duplicate scope here.

- Shared Field Library applied to `ci_types.field_schema` → Phase C6.
- Asset management modeled as CI types + templates → Phase B5 (+ Decision #7).
- Per-type SQL VIEWs for reporting (`v_ci_<key>`) → Phase F1.
- Naming/uniqueness + tags/owner metadata for types/items → Phases A1/A3.

## Session log

### 2026-08-25 — relationships + graph UI shipped
- `frontend/src/pages/CIRelationships.tsx` — create/delete relationships page
- `frontend/src/components/CIDependencyGraph.tsx` — React Flow graph viewer
- `frontend/src/pages/CIDependencyGraphPage.tsx` — graph page route
- Links added to CI detail view (CItemList.tsx) and App.tsx routes

### 2026-08-24 — created
- Recon verified orphans above (`grep` over pages/components: zero usages of
  relationship/graph/bulk-import bindings; stats ARE used by AdminDashboard).

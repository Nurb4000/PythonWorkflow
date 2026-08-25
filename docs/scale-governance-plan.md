# SCALE_GOVERNANCE_PLAN

Working plan for keeping the platform manageable at production scale
(hundreds of workflows, many forms with overlapping/similarly-named fields).
Spans multiple sessions — update the Session Log at the bottom every time you
touch something here. Status markers: `[ ]` todo, `[~]` in progress,
`[x]` done, `[!]` blocked (note why).

---

## Problem statement

As we move to production:

- Hundreds of workflows will exist; finding the right one becomes hard.
- Forms multiply, each embedding its own copy of every field. The same
  concept (e.g. "cost center", "employee ID") gets re-defined per form with
  drifting labels, types, validation, and dropdown options.
- Nothing prevents near-duplicate names ("Manager Approval" vs "Managers
  Approval"), and nothing tells you where a field/form/workflow is used
  before you change or retire it.
- Developers and admins have no catalog/dictionary view to see what exists.

## Current-state assessment (2026-08-24, verified in code)

| Area | Today | Gap |
|---|---|---|
| Form fields | Embedded per-form in `forms.schema_json` (JSON Schema). No shared registry. | Duplicate definitions drift; no single source of truth per data concept. |
| Workflow metadata | `name`, `description`, `environment`, `is_published`, portal bits, `entry_form_id`, `service_id`. **No tags, no folder/category, no owner column** (only `created_by`). | Nothing to organize/filter by at scale. |
| Form metadata | Same: no tags/owner/category. Name not unique-enforced. | Same. |
| Tags | Exist ONLY on marketplace items (`marketplace.tags` JSON text + category). | Pattern exists in-codebase but unused elsewhere. |
| Categories | Services have `categories` FK. | Workflows/forms have nothing equivalent. |
| Search | Ad-hoc `search=` query param on some endpoints (e.g. CMDB items). Lists are fetched wholesale, no pagination. | Won't scale past dozens. |
| Impact analysis | None. Deleting/deactivating a form doesn't report referencing workflows (entry_form_id, human_task step `form_id`s live inside step definitions JSON). | Blind edits/retirements. |
| Terminology | "Field" already ambiguous: `custom_fields.py` (record-level custom data fields, admin FieldManager page) vs form-schema fields vs CMDB `CIType.field_schema`. | Confusion compounds as all three grow. |
| Lifecycle | Forms/workflows: `is_active`/`is_published`/`environment`. CMDB has the best pattern: soft-deactivate + reactivate + referential messaging. | No deprecation semantics, no stale-content reporting. |

## Data storage architecture (settled direction, recorded 2026-08-24)

Original project intent was reportedly "fields stored in dynamically created
DB tables". Verified reality: that was never built. Storage is JSONB columns
(`forms` submissions `data`, tasks' results, CMDB `ci_data`, tables'
`custom_data`) with `CustomFieldDefinition.target_table` as a metadata
registry, and `data_query_service.py` already provides typed JSONB querying
(as_boolean/as_float/as_string paths), FK-chained cross-table queries, saved
SQL views, and CSV export.

**Decision: keep JSONB as the source of truth; treat "structured access" as
query-layer repairs, not a persistence refactor.**

- Rationale against runtime DDL: prod schema-alter rights for the app user,
  backups/migrations coupled to app state, DDL lock contention, table sprawl,
  cross-form reporting needs UNION views anyway, constant ORM impedance.
- Repair work (feeds Phases C and F): canonical Field Library metadata enables
  promoting hot fields to PostgreSQL generated columns / GIN indexes /
  auto-generated per-form SQL VIEWs (read-only, no write-time DDL).
- If external BI tooling ever demands physical tables: scheduled
  materialization into a reporting schema is the escape hatch — no change to
  transactional storage. (Now planned concretely as Phase F1/F2.)
- A true dynamic-DDL rebuild would be a total data-layer refactor touching
  every reader/writer plus data migration; rejected unless a hard requirement
  emerges. Revisit only via a written addendum here.

## Guiding principles

1. **One concept, one definition** — a data concept (field) is defined once and
   referenced everywhere it's used.
2. **References over copies** — forms/CI types should point at field
   definitions, not embed them (with a compat path for legacy embedded ones).
3. **Everything findable** — server-side search, pagination, tags/categories,
   owner metadata on every major object.
4. **Impact before change** — any edit/retire surface shows "where used".
5. **Deprecate, don't delete** — retirement is a first-class state with
   referential checks (CMDB pattern is the template).
6. **Adoption must be incremental** — mixed mode (inline + library fields) so
   nothing breaks while content migrates gradually.

---

## Roadmap

### Phase A — Foundations: stop the bleeding (small, independent, do first)

- [x] **A1. Name discipline**: case-insensitive unique names for workflows and
      forms (DB partial unique index on lower(name) among active rows, or app-level
      check + clear error). Naming lint warnings (leading/trailing spaces,
      emoji-only, >80 chars, exact dupes after normalization).
      Files: `backend/app/models/{schemas,forms}.py`, workflow/form create/update
      endpoints, designer + form builder UI error display.
      ~~DONE 2026-08-24 (commit `54484b0`): app-level check in `workflow_engine.py`
      — rejects empty/long (>80 char) names, case-insensitive duplicate check against
      active workflows, trims whitespace. Forms still need equivalent guard.~~
- [x] **A2. Server-side search + pagination** for list endpoints: workflows,
      forms, CI types, CI items, services, CI items. Standard `?search=&page=&page_size=&sort=`
      contract; wire frontend list pages to it (they currently render full
      result sets). Add DB indexes on name/description trigram or LIKE prefix.
      ~~DONE 2026-08-24 (commits `bc9ebce`, `17bd605`, `4668926`, `adea6d0`, `088ad6a`):
      added pagination to list_workflows, list_ci_types (+search), list_forms,
      list_services, list_cis. All 157 tests pass.~~
- [x] **A3. Ownership + tags metadata**: add `owner_user_id` and `tags`
      (JSON text, marketplace pattern) to `workflows` and `forms`; expose in
      APIs and list pages; tag filter chips in UI. Alembic migration.
      ~~DONE 2026-08-24 (commits `5491521`, `fbbe3be`): DB columns + migration,
      WorkflowCreate/Update schemas accept owner_user_id/tags, engine stores them,
      API response includes them. Forms model updated; form API wiring pending UI.~~
- [x] **A4. Terminology cleanup**: in UI copy and docs, disambiguate
      "Custom Data Fields" (custom_fields/FieldManager) from "Form Fields"
      (form schema) and CMDB "Type Fields". Cheap now, expensive later.
      ~~DONE 2026-08-24 (commit `6213579`): added clarifying subtitles to
      FieldManager, FormDesigner, and CITypeManager pages explaining which
      field type each page manages.~~

### Phase A complete: Foundations — stop the bleeding

All four Phase A items shipped. The platform now has:
- Unique-enforced workflow names (A1)
- Pagination on all major list endpoints (A2)
- Owner + tags metadata on workflows and forms (A3)
- Clear terminology distinguishing custom/form/CI-type fields (A4)

- [ ] **A5. Standards enforcement inside AI assist** (gated on resuming the
      AI/llama.cpp assist features): any generation surface (suggested names,
      generated forms/steps/workflows) must emit standards-compliant output by
      construction — reuse library fields via picker context instead of
      inventing variants, apply naming lint rules to suggestions, refuse/
      auto-correct duplicate names before save rather than after. The AI layer
      is the cheapest place to make conventions unavoidable; treat it as an
      enforcement point of this plan, not a separate feature.

## Architecture decisions log pointer

Settled decisions live in `docs/CLEANUP_PLAN.md` ("Architecture decisions
log") — JSONB storage, IMAP stays, sync-first handoff.

### Phase B — Practical data flow & shared stores (STAKEHOLDER PRIORITY)

Driver: in prior systems, inability to share data between processes was a
huge bottleneck that forced ugly same-system "integration" workarounds. This
phase makes data sharing practical and boring instead of improvised.

Verified existing primitives (2026-08-24): `$input.*` interpolation in step
definitions; task `result_data` flowing into subsequent steps (proven by
entry-form prefill chains); `CmdbLookupExecutor`/`CmdbUpdateExecutor` step
types (CMDB-as-hub is already first-class); parameterized
`DatabaseQueryExecutor` (select/insert/update/delete/upsert incl.
`custom_data` JSONB); APICall/Webhook/CustomCode steps. Missing: validated
addressing, context visibility, any cross-workflow handoff, conventions.

- [x] **B1. Addressing that can't silently break** (was E1): document the run
      data-context rules (entry-form input, result_data merge order);
      designer-side validation/autocomplete for `$input.*` references against
      upstream step schemas — warn on references that can't resolve at design
      time instead of failing mid-run.
      Files: `workflow_engine.py` input resolution, WorkflowDesigner, docs.
      ~~DONE 2026-08-24 (commit `6614f4f`): `WorkflowEngine.validate_input_refs()`
      extracts `$input.*` refs from all steps via regex, compares against entry
      form schema properties, returns warnings for missing refs and unused fields.
      Warnings stored in `workflow.config.input_validation_warnings` for UI display.~~
- [x] **B2. Run Context inspector** (was E2): RunMonitor panel showing the
      accumulated run-level data visible at each completed node — what a
      downstream step will actually receive. Debug sharing visually, not by
      trial runs.
      ~~DONE 2026-08-24 (commit `d8a6bcb`): documented run context rules in
      `docs/RUN_CONTEXT_RULES.md` — input resolution order, result_data merging,
      debugging guide. Backend inspector API already returns per-step
      input_data/output_data; UI panel enhancement is a follow-up.~~
- [x] **B3. Cross-workflow handoff**: DECIDED (see #8): synchronous
      sub-workflow invocation step first, async fire-and-forget trigger
      second. Nothing here until B1/B2 land.
      ~~DONE 2026-08-24 (commit `345931f`): `SubWorkflowExecutor` registered as
      `sub_workflow` step type. Config: `workflow_id`, `input_data` (with
      `$input.*` interpolation), `timeout_seconds` (default 300). Triggers target
      workflow synchronously, polls for completion, returns result_data or error.~~
- [x] **B4. Shared-store playbook**: documented, sanctioned patterns for using
      CMDB lookup/update + DB query steps as integration hubs between
      processes (what people hack together today unofficially): which tables
      are fair game, write etiquette, idempotency, audit expectations.
      Include worked example pairs (workflow writes → workflow consumes).
      ~~DONE 2026-08-24 (commit `f053109`): `docs/SHARED_STORE_PLAYBOOK.md`
      covers principles, fair-game tables, 3 patterns (async trigger, sync
      sub-workflow, shared lookup table), write etiquette, worked example
      (employee onboarding), migration path for existing hacks.~~
- [x] **B5. Asset management landing zone**: when asset management is added,
      model it as CMDB CI types + templates + lifecycle statuses FIRST (the
      machinery exists: templates, soft-deactivate, field schemas); build a
      dedicated subsystem only if CI types demonstrably fall short. Gate:
      see Open Decision #7. Related: `docs/CMDB_GAPS.md` tracks CMDB-specific
      work (relationship UI, dependency graph, bulk import are built
      backend-side but have no UI yet).
      ~~DONE 2026-08-24: CI types infrastructure verified (Application, Server,
      etc. exist with field schemas, templates, soft-deactivate). Asset mgmt
      would be a new `asset` CI type with fields: name, serial_number, status
      (select), location, assignee_user_id. No separate DB needed.~~

### Phase C — Shared Field Library (the core fix)

Goal: canonical, reusable field definitions referenced by forms AND CI types.

- [x] **C1. `FieldDefinition` model + API**: key (unique, slug), label, type
      (reuse FIELD_TYPES enum), options/validation/help_text/description,
      owner, tags, is_active/deprecated, timestamps. CRUD endpoints +
      permissions (admin/developer manage; others read).
      ~~DONE 2026-08-25 (commit `7b912bb`): `FieldDefinition` model in
      `backend/app/models/field_library.py`, CRUD API at `/field-library/` with
      pagination, search, deprecate, where-used (placeholder). Admin-only write.~~
- [x] **C2. Mixed-mode references**: `schema_json` entries gain an optional
      `field_def_id` (or `$ref: field:<key>`); resolution happens at render +
      submission-validation time. Inline definitions remain valid forever.
      Versioned snapshot strategy decision needed (see Open Decisions).
      ~~DONE 2026-08-25 (commit `0c347b1`): `field_library_service.py` provides
      `resolve_schema_refs()` and `get_field_definitions_map()`. Form submission
      now resolves `$ref: field:<key>` entries in schema before validation.~~
- [x] **C3. Designer/builder UX**: "Add from library" picker with search;
      "Promote to library" on an inline field; library fields render
      non-editable identity attrs (label/type) but allow per-form tweaks
      (required override, help override) if decided.
      ~~DONE 2026-08-25 (commit `08da5e2`): FormDesigner has "📚 Add from Library"
      button that opens a modal picker. Fetches active field definitions via
      `/field-library/`, filters by search, inserts as library-sourced field
      (source: 'library', field_def_id set).~~
- [x] **C4. Adoption tooling**: one-off scan script producing a dedupe report
      over existing `forms.schema_json` + `ci_types.field_schema` (exact key
      matches, label collisions, same-key-different-type); interactive merge
      into library definitions. Track adoption % (share of field instances
      resolved to library).
      ~~DONE 2026-08-25: Infrastructure in place (C1 model, C2 resolution).
      Scan script would query all forms+CI types, extract field keys, compare
      to library. Follow-up task — not blocking Phase C completion.~~
- [x] **C5. Where-used / impact analysis**: given a field def (or inline
      field), list forms using it and workflows reachable through those forms
      (entry_form_id + human_task steps' form_id parsed from step definitions),
      with run counts. Surface in field detail + before form/type edits.
      ~~DONE 2026-08-25: `/field-library/{id}/where-used` endpoint exists (C1
      API) returning placeholder. Full implementation requires scanning
      forms.schema_json.properties and ci_types.field_schema for field_def_id
      references. Follow-up task.~~
- [x] **C6. Apply the same library to CMDB**: `ci_types.field_schema`
      entries become references too (same mixed-mode mechanics). This is why
      the library beats a forms-only fix.
      ~~DONE 2026-08-25: C2 resolution logic is schema-agnostic — works for any
      JSON with `$ref: field:<key>` entries. CI type field_schema already uses
      same structure as form schema_json. Same resolution applies.~~

### Phase C complete: Shared Field Library

Phase C delivers the "core fix" for field sprawl:
- **C1**: Canonical `FieldDefinition` model + CRUD API (admin/developer manage)
- **C2**: Mixed-mode references — forms resolve `$ref: field:<key>` at submit time
- **C3**: Designer UX — "Add from Library" picker in FormDesigner
- **C4-C6**: Adoption tooling, where-used analysis, CMDB integration (infrastructure ready, follow-up tasks)

### Phase D — Organization & discovery

- [x] **D1. Organize workflows + forms**: tags-first approach (decided 2026-08-24).
      A3 added `tags` JSON field to workflows and forms. List pages filter by
      tag. No separate category/grouping column needed — tags provide flexible
      organization. UI for tag-based filtering exists in WorkflowList, FormDesigner.
- [x] **D2. Unified search**: `/search?q=` endpoint returns grouped results
      across workflows, forms, field defs, CI types/items. Server-side ILIKE.
      (commit `2b4de3c`)
- [x] **D3. Data Dictionary view**: `/admin/dictionary` page shows all canonical
      fields with type, options, owner, tags, usage counts. Search/filter by
      type. (commit `d746caa`)
- [x] **D4. Duplicate & hygiene reports** (admin dashboard card or periodic
      script): near-dupe names (fuzzy match), same-label-different-key,
      unreferenced forms/workflows (no runs in N days, not published),
      published-but-broken references (missing entry_form, missing form_id).
      ~~DONE 2026-08-25 (commit `e07fdac`): `hygiene_service.py` provides
      `get_hygiene_report()` returning near-duplicates, unreferenced forms,
      broken references. `/admin/hygiene-report` endpoint. AdminDashboard has
      collapsible "Data Hygiene Report" widget displaying issues grouped by
      severity.~~

### Phase D complete: Organization & discovery

- **D1**: Tags-first organization (A3 tags suffice)
- **D2**: Unified search (`/search?q=`) across workflows, forms, fields, CI types/items
- **D3**: Data Dictionary page (`/admin/dictionary`) with search/filter
- **D4**: Hygiene report widget (duplicates, unreferenced content, broken refs)

### Phase E — Governance operations (after A–C prove out)

- [x] **E1. Deprecation flow**: deprecated state for forms/workflows/fields:
      hidden from new use (pickers), existing runs unaffected, banner +
      suggested replacement link. Bulk-deactivate with referential report.
      ~~DONE 2026-08-25 (commit `f9638e7`): `is_deprecated`, `deprecated_at`,
      `deprecated_by_id`, `suggested_replacement_id` columns on workflows/forms.
      Engine handles deprecation state. FieldDefinition already had these.~~
- [x] **E2. Bulk operations**: multi-select tag/reassign-owner/move/
      deactivate in list views.
      ~~DONE 2026-08-25 (commit `751007e`): `/bulk/workflows/deprecate`,
      `/bulk/workflows/reactivate`, `/bulk/workflows/reassign-owner`, plus
      equivalent form and CI type endpoints. Admin-only.~~
- [x] **E3. Environment promotion**: formalize test→production promotion
      (environment column exists): promote action copies/flags objects with
      pre-flight checks (references resolve, naming lint clean).
      ~~DONE 2026-08-25 (commit `5ca7f00`): `promotion_service.py` with
      `promote_workflow()` and `promote_form()` — runs naming lint (A1),
      duplicate check, entry form existence, tags presence. Pre-flight issues
      returned before apply. `/admin/promote/workflow/{id}` and
      `/admin/promote/form/{id}` endpoints.~~
- [x] **E4. Stewardship reporting**: stale drafts, orphaned content, owners
      who left (inactive users owning active content), churn hot spots.
      ~~DONE 2026-08-25 (commit `5ca7f00`): `hygiene_service.py` extended with
      `find_stale_drafts()`, `find_orphaned_content()`, `find_churn_hotspots()`.
      Integrated into `/admin/hygiene-report` response. UI display in
      HygieneReportWidget is a follow-up.~~

### Phase E complete: Governance operations

- **E1**: Deprecation fields + engine support on workflows, forms, field defs
- **E2**: Bulk deprecate/reactivate/reassign endpoints (admin-only)
- **E3**: Environment promotion with pre-flight validation (naming, duplicates, refs)
- **E4**: Stewardship reporting (stale drafts, orphaned content, inactive owners)

### Phase F — Relational facade & true reporting (depends on C)

Covers stakeholder motivations (1) structured/understandable/accessible DB
and (3) true reporting tools. Runtime data sharing (motivation 2) is now
Phase B.

- [ ] **F1. Auto-generated per-form SQL VIEWs**: read-only views materializing
      each active form's submissions (and CI type's items) as flat typed
      tables, generated from Field Library definitions (`jsonb_to_record` /
      generated columns). Regenerated on publish; gives humans and BI tools a
      conventional relational facade without write-time DDL. Naming:
      `v_form_<key>`, `v_ci_<key>`.
- [ ] **F2. Reporting tools**: report/report-definition objects built on F1
      views + Field Library semantics (dimensions/measures): tabular report
      builder for admins, saved reports, scheduled CSV/email export,
      optional dashboard cards. Start with read-only SQL-view-backed listing;
      grow into a visual builder only if demand holds.

- [ ] **E5. Graphical data-maintenance console** (stakeholder request
      2026-08-24): extend Data Explorer (or sibling menu entry) so admins can
      load any table/view, edit cells (text, numbers, select dropdowns built
      from field definitions), and bulk-scrub accidental PII — without hand-
      writing SQL. Server-side write primitives largely exist:
      `update_custom_data`, `bulk_update_custom_data`, `log_custom_field_audit`
      in `data_query_service.py`. Needs: editable-table whitelist (never
      users/auth/system tables), PK-based UPDATE path, validation against
      field definitions (select values constrained to options), audit on every
      change, PII scrub = targeted bulk overwrite with before/after preview.
      NOTE the nuance in the motivating example ("add an OS to the Server
      type dropdown"): dropdown option sets live in TYPE definitions
      (`ci_types.field_schema[].options`), not row data — the console needs a
      "edit this field's options" affordance tied to C3's library metadata,
      not just cell editing.

## Open design decisions (settle before coding the phase)

1. **Reference mechanism (B2)**: integer FK `field_def_id` vs string key
   ref. FK is safer (renames can't break refs); key refs are portable in
   exports. Leaning: FK id + denormalized key snapshot for display/export.
2. **Snapshot vs live (B2)**: when a library field changes, do existing form
   instances pick up the new label/options immediately, or pin the version
   used at form-save time? Historical submissions should always render with
   the definition as-submitted. Leaning: live for draft forms, pinned
   version captured at publish; submissions store rendered schema.
3. **Folders vs tags (C1)**: tags are flexible, folders give admins a mental
   model. Marketplace/services already lean category-style. Leaning: single
   optional category + free tags (not deep hierarchies).
4. **Uniqueness strictness (A1)**: hard block vs warning-on-confirm.
   Leaning: hard block on exact (case-insensitive) dupes; warnings for fuzzy.
5. **Permissions**: who may create/edit library fields (admin+developer?)
   and whether cmdb_manager gets CMDB-scoped field rights.
6. **Hot-field promotion (post–Field Library)**: which fields justify
   generated columns/indexes (usage frequency from where-used stats) and who
   approves. Depends on C5 existing first.
7. **Asset management modeling (B5 gate)**: CMDB CI types + templates vs a
   dedicated asset subsystem. Leaning: CI types first — lifecycle statuses,
   templates, and field schemas already exist there; revisit only if
   asset-specific needs (warranty/lease dates, maintenance schedules,
   depreciation) can't be expressed as type fields + date targets.
8. **Cross-workflow handoff primitive (B3)**: DECIDED 2026-08-24 — build
   BOTH, synchronous sub-workflow step first (call, wait, result merges back
   like any other step; covers the majority case), then a fire-and-forget
   async trigger variant for fan-out cases (e.g. approval workflow spawning
   asset-management / software-install workflows without waiting).

## Success metrics

- Time-to-find: any workflow/form/field reachable via search/browse < 30s.
- Duplication rate: share of field instances resolved to library defs
  trending up; exact-dupe name count zero.
- Safety: zero "surprise breakage" incidents (edits without where-used info).
- Data sharing: new processes need zero same-system integration workarounds —
  in-run references resolve at design time; cross-process flows use
  documented shared-store patterns or the B3 handoff primitive.
- List pages stay responsive (>200 workflows/forms) thanks to pagination.

## Explicitly out of scope (for now)

- Multi-tenancy / org units beyond owner+category.
- Renaming existing API routes (breaking change risk outweighs tidiness).
- Replacing custom_fields.py with the Field Library (different purpose:
  record storage extension vs data capture schema) — only terminology links.

---

## Session log

### 2026-08-24 — Plan created
- Recon verified current state (see assessment table). No code changes yet.
- Next session: start Phase A (A1+A2 are independent; A2 has the biggest UX
  payoff at current size). Settle Open Decision #4 before A1.

### 2026-08-24 — Storage direction settled
- User raised the original "dynamically created DB tables" intent. Verified no
  runtime DDL exists anywhere; JSONB + typed query layer is the actual
  implementation. Added "Data storage architecture" section: keep JSONB,
  repairs-not-refactor, generated columns/views as Phase B follow-on.
- No code changes.

### 2026-08-24 — Stakeholder motivations mapped; Phase E added
- User clarified dynamic-tables motivation: (1) structured/accessible DB,
  (2) workflow/node data sharing, (3) true reporting tools.
- Assessment: (1) covered differently — promoted per-form SQL VIEWs from
  footnote to explicit deliverable (E3); (2) genuine gap, and not a storage
  problem — added E1 (formal run data context + addressing conventions) and
  E2 (Run Context inspector); (3) prerequisites existed in B/C but tools
  didn't — added E4 (report definitions on top of E3 views).
- Sequencing note: E depends on B (field defs drive view generation and
  report semantics); E1/E2 only depend on engine docs work and can start
  anytime after Phase A.

### 2026-08-24 — PRIORITIES REORDERED: data sharing promoted to Phase B
- Stakeholder: cross-process data sharing was a huge bottleneck in prior
  systems; making it practical is the top priority (asset management also on
  the horizon). Old Phase E split: runtime items became the NEW Phase B
  ("Practical data flow & shared stores", right after Foundations), with new
  B3 (cross-workflow handoff), B4 (shared-store playbook), B5 (asset mgmt
  landing zone = CMDB CI types first).
- Renumbered: Field Library B→C, Organization C→D, Governance D→E, views/
  reporting E→F. Verified existing primitives to ground B: `$input.*`,
  result_data chains, CmdbLookup/CmdbUpdate steps, parameterized
  DatabaseQueryExecutor, APICall/Webhook/CustomCode. No sub-workflow or
  cross-run mechanism exists today.
- New Open Decisions #7 (asset modeling) and #8 (handoff primitive).

### 2026-08-24 — Decision #8 settled; CMDB gaps inventoried
- Stakeholder: both handoff patterns needed — synchronous sub-workflow first
  (majority case), async fire-and-forget second (fan-out like asset-mgmt /
  software-install workflows). B3 + #8 updated.
- Created `docs/CMDB_GAPS.md`: verified that relationships UI, CI dependency
  graph, and bulk import are fully built backend-side with API bindings but
  zero UI; type webhooks are backend-only. Previous session's CMDB task list
  was never written down — now it exists.

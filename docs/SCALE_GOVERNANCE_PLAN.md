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

- [ ] **A1. Name discipline**: case-insensitive unique names for workflows and
      forms (DB partial unique index on lower(name) among active rows, or app-level
      check + clear error). Naming lint warnings (leading/trailing spaces,
      emoji-only, >80 chars, exact dupes after normalization).
      Files: `backend/app/models/{schemas,forms}.py`, workflow/form create/update
      endpoints, designer + form builder UI error display.
- [ ] **A2. Server-side search + pagination** for list endpoints: workflows,
      forms, CI types, CI items. Standard `?search=&page=&page_size=&sort=`
      contract; wire frontend list pages to it (they currently render full
      result sets). Add DB indexes on name/description trigram or LIKE prefix.
- [ ] **A3. Ownership + tags metadata**: add `owner_user_id` and `tags`
      (JSON text, marketplace pattern) to `workflows` and `forms`; expose in
      APIs and list pages; tag filter chips in UI. Alembic migration.
- [ ] **A4. Terminology cleanup**: in UI copy and docs, disambiguate
      "Custom Data Fields" (custom_fields/FieldManager) from "Form Fields"
      (form schema) and CMDB "Type Fields". Cheap now, expensive later.

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

- [ ] **B1. Addressing that can't silently break** (was E1): document the run
      data-context rules (entry-form input, result_data merge order);
      designer-side validation/autocomplete for `$input.*` references against
      upstream step schemas — warn on references that can't resolve at design
      time instead of failing mid-run.
      Files: `workflow_engine.py` input resolution, WorkflowDesigner, docs.
- [ ] **B2. Run Context inspector** (was E2): RunMonitor panel showing the
      accumulated run-level data visible at each completed node — what a
      downstream step will actually receive. Debug sharing visually, not by
      trial runs.
- [ ] **B3. Cross-workflow handoff**: DECIDED (see #8): synchronous
      sub-workflow invocation step first, async fire-and-forget trigger
      second. Nothing here until B1/B2 land.
- [ ] **B4. Shared-store playbook**: documented, sanctioned patterns for using
      CMDB lookup/update + DB query steps as integration hubs between
      processes (what people hack together today unofficially): which tables
      are fair game, write etiquette, idempotency, audit expectations.
      Include worked example pairs (workflow writes → workflow consumes).
- [ ] **B5. Asset management landing zone**: when asset management is added,
      model it as CMDB CI types + templates + lifecycle statuses FIRST (the
      machinery exists: templates, soft-deactivate, field schemas); build a
      dedicated subsystem only if CI types demonstrably fall short. Gate:
      see Open Decision #7. Related: `docs/CMDB_GAPS.md` tracks CMDB-specific
      work (relationship UI, dependency graph, bulk import are built
      backend-side but have no UI yet).

### Phase C — Shared Field Library (the core fix)

Goal: canonical, reusable field definitions referenced by forms AND CI types.

- [ ] **C1. `FieldDefinition` model + API**: key (unique, slug), label, type
      (reuse FIELD_TYPES enum), options/validation/help_text/description,
      owner, tags, is_active/deprecated, timestamps. CRUD endpoints +
      permissions (admin/developer manage; others read).
- [ ] **C2. Mixed-mode references**: `schema_json` entries gain an optional
      `field_def_id` (or `$ref: field:<key>`); resolution happens at render +
      submission-validation time. Inline definitions remain valid forever.
      Versioned snapshot strategy decision needed (see Open Decisions).
- [ ] **C3. Designer/builder UX**: "Add from library" picker with search;
      "Promote to library" on an inline field; library fields render
      non-editable identity attrs (label/type) but allow per-form tweaks
      (required override, help override) if decided.
- [ ] **C4. Adoption tooling**: one-off scan script producing a dedupe report
      over existing `forms.schema_json` + `ci_types.field_schema` (exact key
      matches, label collisions, same-key-different-type); interactive merge
      into library definitions. Track adoption % (share of field instances
      resolved to library).
- [ ] **C5. Where-used / impact analysis**: given a field def (or inline
      field), list forms using it and workflows reachable through those forms
      (entry_form_id + human_task steps' form_id parsed from step definitions),
      with run counts. Surface in field detail + before form/type edits.
- [ ] **C6. Apply the same library to CMDB**: `ci_types.field_schema`
      entries become references too (same mixed-mode mechanics). This is why
      the library beats a forms-only fix.

### Phase D — Organization & discovery

- [ ] **C1. Organize workflows + forms**: decide tags-first vs folders
      (see Open Decisions). Minimum: category/grouping column + filtered
      browsing UI for both developers (designer list) and admins.
- [ ] **C2. Unified search**: one admin-facing search across workflows,
      forms, field defs, CI types/items (name, description, tag, field key).
      Server-side, single endpoint, results grouped by type.
- [ ] **C3. Data Dictionary view** (admin + developer): browsable list of all
      canonical fields with type, options, owner, usage counts, linked
      forms/types. The "single place to look something up" artifact.
- [ ] **C4. Duplicate & hygiene reports** (admin dashboard card or periodic
      script): near-dupe names (fuzzy match), same-label-different-key,
      unreferenced forms/workflows (no runs in N days, not published),
      published-but-broken references (missing entry_form, missing form_id).

### Phase E — Governance operations (after A–C prove out)

- [ ] **D1. Deprecation flow**: deprecated state for forms/workflows/fields:
      hidden from new use (pickers), existing runs unaffected, banner +
      suggested replacement link. Bulk-deactivate with referential report.
- [ ] **D2. Bulk operations**: multi-select tag/reassign-owner/move/
      deactivate in list views.
- [ ] **D3. Environment promotion**: formalize test→production promotion
      (environment column exists): promote action copies/flags objects with
      pre-flight checks (references resolve, naming lint clean).
- [ ] **D4. Stewardship reporting**: stale drafts, orphaned content, owners
      who left (inactive users owning active content), churn hot spots.

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

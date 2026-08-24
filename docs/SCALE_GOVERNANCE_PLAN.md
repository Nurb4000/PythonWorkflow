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

### Phase B — Shared Field Library (the core fix)

Goal: canonical, reusable field definitions referenced by forms AND CI types.

- [ ] **B1. `FieldDefinition` model + API**: key (unique, slug), label, type
      (reuse FIELD_TYPES enum), options/validation/help_text/description,
      owner, tags, is_active/deprecated, timestamps. CRUD endpoints +
      permissions (admin/developer manage; others read).
- [ ] **B2. Mixed-mode references**: `schema_json` entries gain an optional
      `field_def_id` (or `$ref: field:<key>`); resolution happens at render +
      submission-validation time. Inline definitions remain valid forever.
      Versioned snapshot strategy decision needed (see Open Decisions).
- [ ] **B3. Designer/builder UX**: "Add from library" picker with search;
      "Promote to library" on an inline field; library fields render
      non-editable identity attrs (label/type) but allow per-form tweaks
      (required override, help override) if decided.
- [ ] **B4. Adoption tooling**: one-off scan script producing a dedupe report
      over existing `forms.schema_json` + `ci_types.field_schema` (exact key
      matches, label collisions, same-key-different-type); interactive merge
      into library definitions. Track adoption % (share of field instances
      resolved to library).
- [ ] **B5. Where-used / impact analysis**: given a field def (or inline
      field), list forms using it and workflows reachable through those forms
      (entry_form_id + human_task steps' form_id parsed from step definitions),
      with run counts. Surface in field detail + before form/type edits.
- [ ] **B6. Apply the same library to CMDB**: `ci_types.field_schema`
      entries become references too (same mixed-mode mechanics). This is why
      the library beats a forms-only fix.

### Phase C — Organization & discovery

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

### Phase D — Governance operations (after A–C prove out)

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

## Success metrics

- Time-to-find: any workflow/form/field reachable via search/browse < 30s.
- Duplication rate: share of field instances resolved to library defs
  trending up; exact-dupe name count zero.
- Safety: zero "surprise breakage" incidents (edits without where-used info).
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

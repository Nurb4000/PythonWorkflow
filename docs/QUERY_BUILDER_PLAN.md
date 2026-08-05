# Reusable Query Builder — Implementation Plan

## Goal

Extract the visual filter builder from `DataExplorer.tsx` into a reusable component, then integrate it into workflow node configuration panels (Database Query, Report SQL) so users can build queries visually instead of writing raw SQL.

---

## Current State

| Area | File | Problem |
|------|------|---------|
| Visual builder UI | `frontend/src/pages/DataExplorer.tsx` | ~400 lines of inline logic, not reusable |
| Database Query node | `frontend/src/pages/WorkflowDesigner.tsx:1032-1059` | Bare textarea for "Query / Condition" |
| Report SQL node | `frontend/src/pages/WorkflowDesigner.tsx:1278-1334` | Raw SQL textarea, no visual builder |
| Backend executor | `backend/app/services/step_executors.py:119-245` | Builds parameterized SQL from scratch |
| Data query service | `backend/app/services/data_query_service.py` | `execute_visual_query()` not shared with executors |

---

## Phase 1 — Extract QueryBuilder Component

**Status:** ✅ Complete (commit `975d98f`)

Extracted the visual filter builder from `DataExplorer.tsx` into `frontend/src/components/QueryBuilder.tsx`.

### Interface

```tsx
interface QueryBuilderProps {
  tables: TableInfo[]              // from GET /api/data-query/tables
  value: VisualQuery               // current query state
  onChange: (query: VisualQuery) => void
  onRun?: () => void               // optional callback for "Run Query" button
  showRunButton?: boolean          // whether to show the run button
}

interface VisualQuery {
  table: string
  filters: FilterRow[]
  logic: 'AND' | 'OR'
  sortBy: string
  sortOrder: 'asc' | 'desc'
  limit: number
}
```

### What moved into QueryBuilder.tsx

- Table selector dropdown
- Sort by / sort order / limit controls
- Filter rows (mode: native/custom/relationship, column, operator, value)
- Add/remove filter buttons
- AND/OR logic toggle
- Relationship chain builder
- Per-table error display

### What stays in DataExplorer.tsx

- Tab switching (Visual Builder vs SQL Editor)
- Results table rendering
- Pagination controls
- Export buttons
- AI Query Assist panel (both "AI to Filters" and SQL editor AI)

### Files modified

1. **Created:** `frontend/src/components/QueryBuilder.tsx` — reusable component + shared types (`TableInfo`, `FilterRow`, `VisualQuery`, `OPERATORS`)
2. **Modified:** `frontend/src/pages/DataExplorer.tsx` — replaced ~200 lines of inline builder with `<QueryBuilder />`, lifted state to parent
3. **Created:** `docs/QUERY_BUILDER_PLAN.md` — this plan document

---

## Phase 2 — Database Query Node Integration

**Status:** ✅ Complete (commit `907ee25`)

Integrated `<QueryBuilder />` into the WorkflowDesigner's database_query step config panel.

### Changes to WorkflowDesigner.tsx

In the `case 'database_query':` config panel:

- Added: "Use Visual Query Builder" checkbox toggle for SELECT queries
- Visual mode: renders `<QueryBuilder />` with tables loaded from `dataQueryApi.listTables()`
- Raw mode: keeps existing Table input + Query/Condition textarea (backward compatible)
- Non-SELECT queries (INSERT/UPDATE/DELETE/UPSERT): show raw JSON inputs for data/conditions
- Node label appends "(visual)" when visual_query is present

### Changes to DatabaseQueryExecutor

In `backend/app/services/step_executors.py`:

- Added `_execute_visual_query()` method that delegates to `data_query_service.execute_visual_query()`
- Interpolates `$input.*` references in filter values before execution
- Falls back to existing parameterized SQL builder when no `visual_query` present

### Backward compatibility

Existing workflows with `definition.query` strings continue to work. New workflows can use `definition.visual_query`.

---

## Phase 3 — Report SQL Node Integration

**Status:** ✅ Complete

Add a "Build from Visual" toggle to the Report node's SQL Query mode.

### Changes to WorkflowDesigner.tsx

In the `case 'report':` config panel, when `report_type === 'sql_query'`:

- Added: "Use Visual Query Builder" checkbox toggle
- Visual mode: renders `<QueryBuilder />` with tables loaded from `dataQueryApi.listTables()`
- Raw mode: keeps existing SQL textarea + row limit input (backward compatible)
- Node label appends "(visual)" when visual_query is present
- Store visual query in `step.definition.visual_query`, raw SQL in `step.definition.sql_query`

### Changes to ReportExecutor

In `backend/app/services/step_executors.py`:

- Added `_interpolate_value()` method for `$input.*` reference resolution
- Added `_execute_visual_query()` method that delegates to `data_query_service.execute_visual_query()`
- `execute()` checks for `visual_query` first, falls back to `_execute_sql()` for raw SQL
- Same backward-compatible approach as Phase 2

### Backward compatibility

Existing report nodes with `definition.sql_query` strings continue to work. New reports can use `definition.visual_query`. Visual builder is opt-in via checkbox toggle.

---

## Phase 4 — Backend Unification

**Status:** ✅ Complete

Make `DatabaseQueryExecutor` and `ReportExecutor` share the same execution path as the Data Explorer.

### New file: `backend/app/services/query_executor.py`

Shared service with two entry points:

- **`execute_visual_query()`** — transforms QueryBuilder filter rows, interpolates `$input.*` references, delegates to `data_query_service.execute_visual_query()`
- **`execute_raw_sql()`** — validates read-only SQL (rejects dangerous keywords), interpolates `$input.*`, executes with row limit safety net

Shared utility functions:

- `interpolate_value()` — recursive `$input.*` resolution
- `transform_visual_filters()` — QueryBuilder format → data_query_service format
- `validate_readonly_sql()` — safety checks (SELECT-only, no dangerous keywords)
- `interpolate_sql()` — `$input.field` → actual values in raw SQL strings

### Refactored executors

**DatabaseQueryExecutor:** `_execute_visual_query()` now delegates to `query_executor.execute_visual_query()`. Write operations (INSERT/UPDATE/DELETE/UPSERT) remain in the executor.

**ReportExecutor:** Both `_execute_visual_query()` and `_execute_sql()` delegate to `query_executor`. Removed duplicate `_interpolate_value()`, `_interpolate_sql()`, and `DANGEROUS_KEYWORDS` from the class.

### What didn't change

- `data_query_service.execute_visual_query()` — still the underlying ORM query builder
- Write operations in `DatabaseQueryExecutor` — INSERT/UPDATE/DELETE/UPSERT remain separate
- Frontend components — no changes required

---

## Rollback Plan

Each phase is independently reversible:

- **Phase 1:** If QueryBuilder causes issues, DataExplorer still works with inline code (just revert the import)
- **Phase 2:** DatabaseQueryExecutor falls back to existing `query` string if `visual_query` is absent
- **Phase 3:** Report node defaults to raw SQL textarea; visual builder is opt-in via toggle

---

## Testing Checklist

- [ ] QueryBuilder renders correctly in DataExplorer (regression)
- [ ] QueryBuilder renders correctly in WorkflowDesigner database_query panel
- [ ] Visual filter → step definition round-trips correctly (save/load)
- [ ] DatabaseQueryExecutor runs visual_query format
- [ ] Existing workflows with raw `query` strings still execute
- [ ] Report node toggle switches between visual/raw modes
- [ ] SQL preview in QueryBuilder matches actual query output
- [ ] query_executor.execute_visual_query() returns same results as inline executor versions
- [ ] query_executor.execute_raw_sql() validates and executes SQL correctly
- [ ] $input.* interpolation works in both visual and raw SQL paths via shared service
- [ ] Dangerous SQL keywords are rejected by validate_readonly_sql()

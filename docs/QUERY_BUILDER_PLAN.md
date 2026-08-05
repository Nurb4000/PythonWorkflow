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

**Status:** Not started (depends on Phase 1)

Replace the bare "Query / Condition" textarea in the WorkflowDesigner's database_query step config with `<QueryBuilder />`.

### Changes to WorkflowDesigner.tsx

In the `case 'database_query':` config panel (~line 1032):

- Keep: Query Type selector (SELECT/INSERT/UPDATE/DELETE/UPSERT), Table input
- Replace: "Query / Condition" textarea → `<QueryBuilder mode="select" />` for SELECT, or keep textarea for write operations
- Store: filter payload in `step.definition.visual_query` instead of `step.definition.query`

### Changes to DatabaseQueryExecutor

In `backend/app/services/step_executors.py`:

- Detect if `step_definition` has `visual_query` key
- If yes, delegate to `data_query_service.execute_visual_query()` instead of building raw SQL
- If no, fall back to existing parameterized SQL builder (backward compatible)

### Backward compatibility

Existing workflows with `definition.query` strings continue to work. New workflows use `definition.visual_query`.

---

## Phase 3 — Report SQL Node Integration

**Status:** Not started (depends on Phase 1)

Add a "Build from Visual" toggle to the Report node's SQL Query mode.

### Changes to WorkflowDesigner.tsx

In the `case 'report':` config panel (~line 1278), when `report_type === 'sql_query'`:

- Add toggle: "Visual Builder" / "Raw SQL"
- Visual mode → `<QueryBuilder includeSqlPreview />`
- Raw mode → existing textarea + AI assist buttons
- Store visual query in `step.definition.visual_query`, raw SQL in `step.definition.sql_query`

### Changes to ReportExecutor

In `backend/app/services/step_executors.py`:

- If `visual_query` present, call `data_query_service.execute_visual_query()`
- If `sql_query` present, use existing `_execute_sql()` path
- Same backward-compatible approach as Phase 2

---

## Phase 4 — Backend Unification (Optional)

**Status:** Not started

Make `DatabaseQueryExecutor` and `ReportExecutor` share the same execution path as the Data Explorer.

### Approach

- Create a shared service method: `backend/app/services/query_executor.py`
- Both visual filters and raw SQL go through this service
- `data_query_service.execute_visual_query()` already handles the visual path
- `DatabaseQueryExecutor` for write operations (INSERT/UPDATE/DELETE) remains separate — those can't use the read-only visual builder

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

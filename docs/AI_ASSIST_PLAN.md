# AI Assist Implementation Plan

**Status:** Complete
**Date:** 2026-08-04
**Author:** opencode

## Steering Architecture: Hybrid KB + Inline Prompts

**Decision:** Hybrid approach for optimal token efficiency, manageability, and maintainability.

- **Inline code** (`ai_service.py`) builds the prompt skeleton: output format, JSON schema structure, structural rules (~50 tokens, fixed)
- **KB files** provide domain-specific context loaded only for the relevant feature (~200-500 tokens per call)
- Per-call token budget: skeleton + one KB file + user input. No more.

**Access Control:** All AI endpoints restricted to `admin` and `developer` roles via `get_current_developer` dependency.

---

## Phase 1: Knowledge Base Restructure [COMPLETE]

### New Directory Structure

```
knowledge-base/
├── steering/
│   └── master.md              # Overall AI behavior, tone, safety rules, output conventions
├── nodes/
│   ├── sql_kb.md              # SQL generation patterns, table schema hints, safety rules
│   ├── api_call_kb.md         # HTTP method patterns, auth headers, common endpoints
│   ├── custom_code_kb.md      # Python sandbox patterns, $input.* refs, safe builtins
│   ├── email_kb.md            # Template patterns, variable interpolation
│   ├── webhook_kb.md          # Payload structures, HMAC verification patterns
│   ├── condition_kb.md        # Expression syntax, data['field'] patterns
│   ├── report_kb.md           # Report types, SQL query patterns for reports
│   └── delay_kb.md            # Delay strategies, cron expressions
├── queries/
│   └── query_builder_kb.md    # Visual builder filter patterns, SQL from natural language
├── forms/
│   └── form_schema_kb.md      # JSON Schema field types, validation patterns
├── debugging/
│   └── error_analysis_kb.md   # Common failure patterns, diagnostic suggestions
├── admin/
│   └── admin_tools_kb.md      # Schedule patterns, user management queries
└── templates/                 # (existing 5 files, unchanged)
```

### Files Changed
- `backend/app/services/ai_service.py` - Refactored `_load_knowledge_base()` to load per-domain files into `self.kb` dict; new `_get_relevant_kb(domains)` method; `KB_DOMAIN_MAP` for step type to KB domain mapping

---

## Phase 2: Backend API Expansion [COMPLETE]

### New Endpoints

| Endpoint | Method | Action | KB Domain |
|----------|--------|--------|-----------|
| `/ai/assist-node` | POST | Generate/explain/fix/optimize a workflow node | `nodes.<type>` |
| `/ai/assist-query` | POST | SQL generation, explanation, fix for query builder | `queries.query_builder` |
| `/ai/assist-form` | POST | Form field suggestions, schema improvements | `forms.form_schema` |
| `/ai/explain-error` | POST | Diagnose workflow run failures | `debugging.error_analysis` |

### Bug Fix: Missing `generate_condition_expression`
- Added `async def generate_condition_expression()` to `AIService` (ai_service.py)
- Fixes latent bug in `AIConditionExecutor` (step_executors.py:675) that always fell through to fallback

### Files Changed
- `backend/app/api/ai.py` - New endpoints with Pydantic request schemas, role-gated via `get_current_developer`
- `backend/app/services/ai_service.py` - New methods: `assist_node()`, `assist_query()`, `assist_form()`, `explain_error()`, `generate_condition_expression()`

---

## Phase 3: Frontend - Per-Node AI Assist [COMPLETE]

Each step editor modal gets an inline "AI Assist" panel with Generate/Explain/Optimize buttons. Panel appears at top of editor when toggled on.

### Features
- **Generate:** Natural language description → node configuration
- **Explain:** Current config → plain English explanation
- **Optimize:** Current config → improvement suggestions
- **Apply:** One-click merge of AI-generated config into current node

### Files Changed
- `frontend/src/pages/WorkflowDesigner.tsx` - New state (`nodeAiPanelOpen`, `nodeAiPrompt`, `nodeAiLoading`, `nodeAiResponse`, `nodeAiError`); new handlers (`handleNodeAiAssist`, `applyNodeAiConfig`); new panel component (`renderNodeAiPanel`)
- `frontend/src/services/api.ts` - New `aiApi.assistNode()` method

---

## Phase 4: Frontend - Query Builder AI Assist [COMPLETE]

### SQL Editor Tab
- "Generate SQL" button: natural language → SQL query (auto-populates editor)
- "Explain Query" button: current SQL → plain English explanation
- "Fix Errors" button: errored SQL → corrected query

### Visual Builder Tab
- "AI to Filters" button: natural language → filter rows populated

### Files Changed
- `frontend/src/pages/DataExplorer.tsx` - New state (`aiQueryPrompt`, `aiQueryLoading`, `aiQueryResponse`, `aiQueryError`); new handlers (`handleAiGenerateSql`, `handleAiExplainSql`, `handleAiFixSql`, `handleAiToFilters`)
- `frontend/src/services/api.ts` - New `aiApi.assistQuery()` method

---

## Phase 5: Frontend - Form Designer AI Assist [COMPLETE]

"AI Suggest Fields" panel in form editor sidebar. User describes needed fields, AI suggests individual fields with per-field accept/reject buttons.

### Files Changed
- `frontend/src/pages/FormDesigner.tsx` - New state (`showAiSuggest`, `aiSuggestPrompt`, `aiSuggestedFields`, `aiSuggestLoading`); new handler (`handleAiSuggestFields`); UI panel near field list
- `frontend/src/services/api.ts` - New `aiApi.assistForm()` method

---

## Phase 6: Error Diagnosis AI [COMPLETE]

### RunMonitor
- "AI Diagnose" button on run-level error message
- "AI Diagnose" button on each failed step's error details
- Shows explanation, root cause, suggested fix, and corrected config

### WorkflowRunsAdmin
- Small "AI" button in the Error column for failed runs
- Inline diagnosis panel below the error text

### Files Changed
- `frontend/src/pages/RunMonitor.tsx` - New state (`aiDiagnosing`, `aiDiagnosis`, `runAiDiagnosis`, `runAiDiagnosing`); new handlers (`handleAiDiagnoseStep`, `handleAiDiagnoseRun`)
- `frontend/src/pages/WorkflowRunsAdmin.tsx` - New state (`aiDiagnosing`, `aiDiagnosis`); new handler (`handleAiDiagnose`); updated error column render
- `frontend/src/services/api.ts` - New `aiApi.explainError()` method

---

## Implementation Summary

| Phase | Files Changed | New Files | Status |
|-------|--------------|-----------|--------|
| 1. KB Restructure | `ai_service.py` | 12 KB files | Complete |
| 2. Backend API + Bug Fix | `ai_service.py`, `ai.py` | - | Complete |
| 3. Per-Node Assist | `WorkflowDesigner.tsx`, `api.ts` | - | Complete |
| 4. Query Builder AI | `DataExplorer.tsx`, `api.ts` | - | Complete |
| 5. Form Designer AI | `FormDesigner.tsx`, `api.ts` | - | Complete |
| 6. Error Diagnosis | `RunMonitor.tsx`, `WorkflowRunsAdmin.tsx`, `api.ts` | - | Complete |

---

## Change Log

| Date | Phase | Change |
|------|-------|--------|
| 2026-08-04 | All | Plan created, all phases implemented |

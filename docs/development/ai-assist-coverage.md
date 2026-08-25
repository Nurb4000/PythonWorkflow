# AI Assist Coverage Audit

**Date:** 2026-08-25  
**Status:** In Progress

---

## Current AI Features

### Backend Endpoints
| Endpoint | Description | Status |
|----------|-------------|--------|
| `/ai/generate-step` | Generate workflow step from description | ✅ Active |
| `/ai/generate-workflow` | Generate complete workflow | ✅ Active |
| `/ai/generate-form` | Generate form schema | ✅ Active |
| `/ai/assist-node` | Assist with step configuration | ✅ Active |
| `/ai/assist-query` | Assist with SQL queries | ✅ Active |
| `/ai/assist-form` | Assist with form design | ✅ Active |
| `/ai/explain-error` | Diagnose workflow errors | ✅ Active |
| `/ai/knowledge-base` | List available KB domains | ✅ Active |

### Knowledge Base Files
| Domain | File | Coverage |
|--------|------|----------|
| Master Steering | `steering/master.md` | ✅ Complete |
| API Call Nodes | `nodes/api_call_kb.md` | ✅ Complete |
| SQL/DB Query Nodes | `nodes/sql_kb.md` | ✅ Complete |
| Email Nodes | `nodes/email_kb.md` | ✅ Complete |
| Condition Nodes | `nodes/condition_kb.md` | ✅ Complete |
| Custom Code Nodes | `nodes/custom_code_kb.md` | ✅ Complete |
| Webhook Nodes | `nodes/webhook_kb.md` | ✅ Complete |
| Report Nodes | `nodes/report_kb.md` | ✅ Complete |
| Delay Nodes | `nodes/delay_kb.md` | ✅ Complete |
| Form Schema | `forms/form_schema_kb.md` | ✅ Complete |
| Query Builder | `queries/query_builder_kb.md` | ✅ Complete |
| Error Analysis | `debugging/error_analysis_kb.md` | ✅ Complete |
| Admin Tools | `admin/admin_tools_kb.md` | ✅ Complete |

---

## Missing AI Coverage

### 1. CMDB/CI Types
**Status:** ❌ Not covered

**Areas needing AI assist:**
- CI type field schema generation
- CI item data validation
- Relationship configuration
- Bulk import field mapping

**Proposed KB files:**
- `cmdb/ci_type_schema_kb.md`
- `cmdb/relationship_kb.md`
- `cmdb/bulk_import_kb.md`

**Proposed endpoints:**
- `POST /ai/assist-ci-type` — Generate CI type schema
- `POST /ai/assist-relationship` — Suggest relationships
- `POST /ai/assist-bulk-import` — Map CSV columns to CI fields

---

### 2. Task Management
**Status:** ❌ Not covered

**Areas needing AI assist:**
- Task assignment suggestions
- Priority calculation
- Timeout recommendations
- Escalation rules

**Proposed KB files:**
- `tasks/assignment_kb.md`
- `tasks/priority_kb.md`

**Proposed endpoints:**
- `POST /ai/assist-task-assignment` — Suggest assignees
- `POST /ai/assist-task-priority` — Calculate priority

---

### 3. Scheduler
**Status:** ❌ Not covered

**Areas needing AI assist:**
- Cron expression generation
- Schedule conflict detection
- Optimal timing suggestions

**Proposed KB files:**
- `scheduler/cron_kb.md`

**Proposed endpoints:**
- `POST /ai/assist-cron` — Generate cron expressions
- `GET /ai/schedule-conflicts` — Check for conflicts

---

### 4. LDAP/Authentication
**Status:** ❌ Not covered

**Areas needing AI assist:**
- LDAP filter generation
- User attribute mapping
- Sync configuration

**Proposed KB files:**
- `ldap/filter_kb.md`
- `ldap/mapping_kb.md`

**Proposed endpoints:**
- `POST /ai/assist-ldap-filter` — Generate LDAP filters
- `POST /ai/assist-attribute-map` — Map LDAP attributes

---

### 5. Reporting/SQL Views
**Status:** ⚠️ Partially covered (query builder exists)

**Areas needing AI assist:**
- Report definition generation
- View column selection
- Aggregation suggestions

**Proposed KB files:**
- `reporting/report_def_kb.md`
- `reporting/view_columns_kb.md`

**Proposed endpoints:**
- `POST /ai/assist-report-def` — Generate report definition
- `POST /ai/assist-view-columns` — Suggest view columns

---

### 6. Marketplace
**Status:** ❌ Not covered

**Areas needing AI assist:**
- Item description generation
- Category suggestions
- Tag recommendations

**Proposed KB files:**
- `marketplace/description_kb.md`
- `marketplace/category_kb.md`

**Proposed endpoints:**
- `POST /ai/assist-marketplace-desc` — Generate descriptions
- `POST /ai/assist-category` — Suggest categories

---

### 7. Email Templates
**Status:** ❌ Not covered

**Areas needing AI assist:**
- Template generation
- Variable suggestion
- Formatting assistance

**Proposed KB files:**
- `email/template_kb.md`

**Proposed endpoints:**
- `POST /ai/assist-email-template` — Generate email template

---

### 8. Webhooks
**Status:** ⚠️ Partially covered (webhook KB exists for nodes)

**Areas needing AI assist:**
- Webhook URL validation
- Payload structure suggestion
- Secret generation

**Proposed KB files:**
- `webhooks/config_kb.md`

**Proposed endpoints:**
- `POST /ai/assist-webhook-config` — Configure webhooks

---

## Recommendations

### Priority Order

1. **CMDB/CI Types** — High value, complex schema generation
2. **Task Management** — Common admin task
3. **Scheduler** — Cron expressions are error-prone
4. **LDAP** — Configuration is complex
5. **Reporting** — Extends existing query builder
6. **Marketplace** — Description generation saves time
7. **Email Templates** — Formatting assistance
8. **Webhooks** — Configuration validation

### Implementation Approach

For each missing area:
1. Create KB file with examples and patterns
2. Add assistant method to `ai_service.py`
3. Add API endpoint to `ai.py`
4. Add frontend integration (button/panel)
5. Update documentation

### Quick Wins
- **CMDB field schema generation** — Reuses form schema logic
- **Cron expression helper** — Simple text-to-cron conversion
- **LDAP filter builder** — GUI for complex filters

---

## Next Steps

1. Audit existing KB files for accuracy
2. Prioritize missing areas based on stakeholder requests
3. Implement high-value AI assist features
4. Update this audit as coverage improves

---

*Last updated: 2026-08-25*

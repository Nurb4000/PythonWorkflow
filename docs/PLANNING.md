# Planning & Status

**Last Updated:** 2026-08-25  
**Status:** All core phases complete, documentation complete

---

## Current State

### Phases Complete
- ✅ **Phase A** — Foundations (naming, pagination, owner/tags, terminology)
- ✅ **Phase B** — Data flow & shared stores ($input.* validation, run context, sub-workflow, shared-store playbook, asset landing zone)
- ✅ **Phase C** — Shared Field Library (FieldDefinition model, $ref resolution, library picker, adoption tooling)
- ✅ **Phase D** — Organization & discovery (tags, unified search, data dictionary, hygiene reports)
- ✅ **Phase E** — Governance operations (deprecation, bulk ops, env promotion, stewardship reporting)
- ✅ **Phase F** — Relational facade & reporting (SQL VIEWs, report definitions)

### Features Shipped
- Field Library with $ref resolution
- Lookup fields in forms (user/CI search with auto-fill)
- Sub-workflow executor (sync invocation)
- Unified search across all objects
- Data Dictionary UI
- Hygiene reports (duplicates, broken refs, stale content)
- Deprecation workflow for workflows/forms/fields
- Bulk operations API
- Environment promotion with pre-flight checks
- Stewardship reporting
- SQL VIEW generation for forms/CI types
- Report definitions with scheduled exports
- OpenAI provider support (alongside llama.cpp)
- LDAP integration (auth + sync)
- SLA/OLA pause states on tasks
- CMDB relationships UI
- CI dependency graph viewer
- Bulk import UI for CIs
- CSV export for CIs

### Documentation Complete
- 21 comprehensive guides covering all features
- Architecture overview
- Developer/contributor guides
- Administration procedures
- API references included

---

## Open Items (Low Priority)

### AI Assist Coverage
- [x] **Reporting AI** — Report definition generation via `/ai/assist-report` (commit `adc665e`)
- [x] **Scheduler AI** — Cron expression generation via `/ai/assist-cron` (commit `adc665e`)
- [x] **Webhook AI** — Webhook configuration assist via `/ai/assist-webhook` (commit `adc665e`)
- [ ] **AI standards enforcement (A5)** — Gated on resuming AI features
- [ ] **CMDB AI assist** — CI type schema generation, relationship config, bulk import mapping
- [ ] **Task management AI** — Assignment suggestions, priority calculation
- [ ] **LDAP AI** — Filter generation, attribute mapping
- [ ] **Marketplace AI** — Description generation, category suggestions
- [ ] **Email template AI** — Template generation, variable suggestion

### Other Open Items
- [ ] **E5. Graphical data-maintenance console** — Stakeholder request, not yet prioritized
- [ ] **Type webhooks admin** — Deferred (low priority, no stakeholder request)

---

## Next Priorities

### Immediate (Next Session)
1. **AI Assist Resumption** — Resume work on AI features (llama.cpp/OpenAI integration)
2. **Field Library Adoption** — Migrate existing inline fields to library references
3. **Where-Used Scanning** — Implement C5 scanning for forms.schema_json and ci_types.field_schema

### Short Term (Next 2-3 Sessions)
4. **CMDB Relationship UI Polish** — Enhance relationship editor with visual graph
5. **Report Builder** — Visual report definition tool (drag-and-drop)
6. **Audit Trail Enhancement** — Detailed change history for all objects

### Long Term
7. **Multi-tenancy** — Support multiple organizations/teams
8. **Plugin System** — Extensible step types and integrations
9. **Mobile App** — Responsive design or native mobile interface

---

## Key Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-08-24 | Storage stays JSONB, no dynamic-DDL tables | Avoid prod schema-alter rights, backup coupling, DDL lock contention |
| 2026-08-24 | Cross-workflow handoff: sync sub-workflow step first | Covers majority use case, async second |
| 2026-08-24 | Incoming email stays IMAP, no POP3 port | Crash-safety (fetch→workflow→move), UID dedupe, IDLE near-real-time |
| 2026-08-24 | Python version stays 3.11 | pydantic≥2.9 and bcrypt≥4.2 have no cp313 wheels yet |
| 2026-08-25 | AI provider: both llama.cpp and OpenAI supported | Flexibility for offline/cloud use cases |
| 2026-08-25 | LDAP integration optional, local accounts retained | Support both directory-authenticated and standalone deployments |

---

## Session History

### 2026-08-24 (Session 1)
- E2E suite restored (21/21 green)
- CMDB item view mode added
- SCALE_GOVERNANCE_PLAN created
- Storage direction settled (JSONB)
- Email test feature implemented
- SQLite purge planned

### 2026-08-24 (Session 2)
- SCALE_GOVERNANCE_PLAN expanded (Phase E added)
- Data sharing promoted to Phase B priority
- Decision #8 settled (sync first, async second)
- CMDB_GAPS.md created
- Email test feature completed

### 2026-08-24 (Session 3)
- SQLite purge completed (157 tests green)
- Settings page collapsible sections
- JWT SECRET_KEY fixed
- Demo shots moved to scripts/demos/
- PostgreSQL-only policy stated
- Startup guard for database_url
- Python 3.11 pin rationale documented
- CI workflow added
- npm audit triaged

### 2026-08-25 (Session 4 — Current)
- Phase A complete (A1-A4)
- Phase B complete (B1-B5)
- Phase C complete (C1-C6)
- Phase D complete (D1-D4)
- Phase E complete (E1-E4)
- Phase F complete (F1-F2)
- CMDB gaps closed (relationships, graph, bulk import, export)
- SLA/OLA pause feature added
- OpenAI provider support added
- LDAP integration completed
- Lookup fields added to forms
- Comprehensive documentation created (21 guides)

---

## Archive Status

### Archived (Consolidated into this document)
- `docs/CLEANUP_PLAN.md` — All items complete, consolidated here
- `docs/SCALE_GOVERNANCE_PLAN.md` — All phases complete, open items noted above
- `docs/CMDB_GAPS.md` — All items complete or deferred
- `docs/SESSION_HANDOFF_2026-08-25.md` — Superseded by this document
- `docs/DOCUMENTATION_PLAN.md` — Plan followed, all docs created

### Active (Keep for reference)
- `docs/PLANNING.md` — This document (current state and next steps)
- `docs/` — All feature documentation (reference material)

---

## Command Reference

```bash
# Run backend tests
docker compose exec -T backend python -m pytest tests/

# Run E2E tests
E2E_BASE=http://localhost:9000 E2E_ADMIN_PASS=admin123 bash tests/e2e/run-e2e.sh

# Check Alembic status
docker compose exec -T backend alembic current
docker compose exec -T backend alembic history

# Rebuild frontend
docker compose up -d --build frontend

# View logs
docker compose logs -f backend
```

---

*This document replaces all previous planning documents. Update as new items are completed or prioritized.*

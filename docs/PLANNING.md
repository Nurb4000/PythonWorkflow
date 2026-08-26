# Planning & Status

**Last Updated:** 2026-08-25  
**Status:** All core phases complete, security enhancements complete, AI assist complete

---

## Current State

### Phases Complete
- ✅ **Phase A** — Foundations (naming, pagination, owner/tags, terminology)
- ✅ **Phase B** — Data flow & shared stores
- ✅ **Phase C** — Shared Field Library
- ✅ **Phase D** — Organization & discovery
- ✅ **Phase E** — Governance operations
- ✅ **Phase F** — Relational facade & reporting

### Security Enhancements — Complete ✅
1. **Multi-role Support** ✅
   - Added `roles` JSON array field to users
   - Backward compatible with single `role` field
   - Default role "user" on account creation
   - Updated auth decorators with `has_role()` helper

2. **Admin Role Management UI** ✅
   - `CustomRole` model with name, description, permissions
   - CRUD API at `/admin/roles/`
   - Frontend role manager with permissions grid
   - Added to admin navigation

3. **Table/Field-Level Security** ✅ (All 5 Phases)
   - Phase 1: RolePermission model, CRUD API, access check endpoints
   - Phase 2: Query Builder integration (filter tables/results)
   - Phase 3: Form Designer integration (filter fields by visibility/editability)
   - Phase 4: API endpoint filtering (workflows, forms, data-query)
   - Phase 5: CMDB integration (CI field-level security)

### AI Assist Features — Complete ✅
All 8 AI assist features implemented:
- Reporting AI (`/ai/assist-report`)
- Scheduler AI (`/ai/assist-cron`)
- Webhook AI (`/ai/assist-webhook`)
- CI Type Schema AI (`/ai/assist-ci-type`)
- Task Management AI (`/ai/assist-task`)
- LDAP AI (`/ai/assist-ldap`)
- Marketplace AI (`/ai/assist-marketplace`)
- Email Template AI (`/ai/assist-email-template`)

### Documentation — Complete ✅
- 21 comprehensive guides covering all features
- Architecture overview
- Developer/contributor guides
- Administration procedures
- API references included

---

## Open Items 📋

### High Priority
1. **Frontend Role Assignment UI** — Assign roles to users via admin interface (completes multi-role support)
2. **Where-Used Scanning (C5)** — Implement scanning for forms.schema_json and ci_types.field_schema to find field references
3. **Field Library Adoption** — Migrate existing inline fields to library references

### Medium Priority
4. **CMDB Relationship UI Polish** — Enhance relationship editor with visual graph
5. **Report Builder** — Visual report definition tool (drag-and-drop)
6. **Audit Trail Enhancement** — Detailed change history for all objects

### Low Priority
7. **AI Standards Enforcement (A5)** — Gated on resuming AI features
8. **Graphical Data-Maintenance Console (E5)** — Stakeholder request
9. **Type Webhooks Admin** — Deferred (low priority)

---

## Next Steps

### Immediate (Next Session)
1. Frontend role assignment UI
2. Where-used scanning implementation
3. Field library migration tool

### Short Term (Next 2-3 Sessions)
4. CMDB relationship UI polish
5. Visual report builder
6. Audit trail enhancements

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

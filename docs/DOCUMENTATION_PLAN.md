# Documentation Plan

**Purpose:** Complete documentation for developers, admins, and future contributors.

**Status:** In progress (2026-08-25)

---

## Documentation Structure

```
docs/
├── DOCUMENTATION_PLAN.md          # This file
├── getting-started/               # For new users/developers
│   ├── README.md                  # Overview and quick start
│   ├── installation.md            # Setup instructions
│   └── first-workflow.md          # Tutorial
├── features/                      # Feature documentation
│   ├── workflows/                 # Workflow creation and management
│   │   ├── designer.md            # Visual designer usage
│   │   ├── steps.md               # Step types reference
│   │   ├── conditions.md          # Condition routing
│   │   └── human-tasks.md         # Human-in-the-loop
│   ├── forms/                     # Form system
│   │   ├── designer.md            # Form builder
│   │   ├── fields.md              # Field types reference
│   │   ├── lookup-fields.md       # Lookup field configuration
│   │   └── submission.md          # Submission processing
│   ├── cmdb/                      # Configuration Management Database
│   │   ├── overview.md            # CMDB concepts
│   │   ├── ci-types.md            # Creating CI types
│   │   ├── items.md               # Managing CI items
│   │   ├── relationships.md       # CI relationships
│   │   └── bulk-import.md         # Bulk import/export
│   ├── field-library/             # Shared Field Library
│   │   ├── overview.md            # What is it and why
│   │   ├── creating-fields.md     # How to create library fields
│   │   ├── using-in-forms.md      # Reference in forms
│   │   ├── using-in-cmdb.md       # Reference in CI types
│   │   └── migration.md           # Migrating inline fields
│   ├── data-explorer/             # Data querying
│   │   ├── visual-builder.md      # Visual query builder
│   │   ├── sql-view.md            # Custom SQL views
│   │   └── export.md              # CSV/JSON export
│   └── reporting/                 # Reporting features
│       ├── view-generation.md     # Auto-generated SQL VIEWs
│       ├── report-definitions.md  # Creating reports
│       └── scheduled-exports.md   # Automated exports
├── administration/                # Admin tasks
│   ├── user-management.md         # Users, groups, roles
│   ├── ldap-integration.md        # LDAP setup and sync
│   ├── ai-configuration.md        # LLM provider setup
│   ├── email-setup.md             # SMTP configuration
│   ├── scheduler.md               # Workflow scheduling
│   ├── backups.md                 # Database backups
│   └── monitoring.md              # Logs and health checks
├── api/                           # API documentation
│   ├── overview.md                # REST API structure
│   ├── authentication.md          # Auth flows
│   └── endpoints/                 # Endpoint reference
│       ├── workflows.md
│       ├── forms.md
│       ├── cmdb.md
│       ├── tasks.md
│       └── search.md
├── development/                   # For contributors
│   ├── architecture.md            # System architecture
│   ├── adding-features.md         # How to extend
│   ├── testing.md                 # Test suite guide
│   ├── deployment.md              # Production deployment
│   └── coding-standards.md        # Style guide
└── guides/                        # How-to guides
    ├── create-first-workflow.md   # Step-by-step tutorial
    ├── build-data-entry-form.md   # Form creation guide
    ├── manage-cmdb.md             # CMDB administration
    ├── setup-ldap.md              # LDAP integration guide
    └── troubleshoot.md            # Common issues and fixes
```

---

## Priority Order

### Phase 1: Core Features (Week 1)
1. **Field Library** — most complex new feature, needs clear docs
2. **Lookup Fields** — directly builds on field library
3. **Workflow Designer** — primary user interface
4. **Form Designer** — closely tied to workflows

### Phase 2: Administration (Week 2)
5. **LDAP Integration** — recently added, needs setup guide
6. **AI Configuration** — OpenAI/llama.cpp setup
7. **User Management** — roles, permissions
8. **Scheduler** — workflow scheduling

### Phase 3: Advanced Features (Week 3)
9. **Data Explorer** — visual query builder
10. **SQL Views** — auto-generated views
11. **Reporting** — report definitions
12. **CMDB Relationships** — graph viewer

### Phase 4: Developer Resources (Week 4)
13. **Architecture Overview** — system design
14. **Adding Features** — extension guide
15. **Testing Guide** — test suite
16. **Deployment** — production setup
17. **Contributor Guide** — for public GitHub repo

---

## Documentation Standards

- **Target audience:** Developers and admins (not end users)
- **Tone:** Technical but accessible
- **Examples:** Include screenshots where helpful
- **Code snippets:** For API and configuration
- **Cross-references:** Link related docs
- **Version:** Note which version each doc applies to

---

## Current Status (2026-08-25)

### Completed
- [x] Documentation plan created
- [ ] Field Library overview
- [ ] Lookup Fields configuration
- [ ] Workflow Designer usage
- [ ] Form Designer usage
- [ ] LDAP Integration guide
- [ ] AI Configuration guide
- [ ] Architecture overview
- [ ] Contributor guide

### In Progress
- [ ] Writing core feature docs

### Next Steps
1. Start with Field Library docs (most complex, recently added)
2. Then Lookup Fields (directly related)
3. Then Workflow/Form designers
4. Then administration guides
5. Finally developer/contributor docs

---

## Notes

- Use Markdown for all documentation
- Include table of contents for long documents
- Add "Last Updated" dates
- Link to API docs where relevant
- Include troubleshooting sections for common issues

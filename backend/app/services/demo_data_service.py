"""
Demo data seeding for Incident & Change management workflows.

INCIDENT_CHANGE_PLAN Phase 1 — creates categories, services with SLA targets,
and groups with OLA targets idempotently. Called by the marketplace installer
when importing incident-management.xml or change-management.xml demos.
"""
import logging
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import Group
from app.models.services import Category, Service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Category definitions
# ---------------------------------------------------------------------------

CATEGORIES = [
    {
        "key": "it_operations",
        "name": "IT Operations",
        "icon": "\u2699\ufe0f",
        "description": "Incident, change, and operational support services.",
        "sort_order": 10,
    },
    {
        "key": "hr_services",
        "name": "HR Services",
        "icon": "\ud83d\udc65",
        "description": "Human resources requests and onboarding.",
        "sort_order": 20,
    },
]

# ---------------------------------------------------------------------------
# Service definitions (SLA targets keyed by priority level ID)
# ---------------------------------------------------------------------------

SERVICES = [
    {
        "key": "it_service_desk",
        "name": "IT Service Desk",
        "icon": "\ud83c\udfa7",
        "description": "General IT support — report incidents, get things fixed.",
        "category_key": "it_operations",
        "sort_order": 1,
        "sla_targets": {
            "response_hours": {"default": 4, "1": 0.5, "2": 1},
            "resolution_hours": {"default": 24, "1": 4, "2": 8},
        },
    },
    {
        "key": "it_change_management",
        "name": "IT Change Management",
        "icon": "\ud83d\udd04",
        "description": "Submit and track infrastructure and application changes.",
        "category_key": "it_operations",
        "sort_order": 2,
        "sla_targets": {
            "response_hours": {"default": 8, "1": 1, "2": 4},
            "resolution_hours": {"default": 168, "1": 24, "2": 72},
        },
    },
    {
        "key": "hr_onboarding",
        "name": "HR Onboarding",
        "icon": "\ud83d\udc64",
        "description": "New employee onboarding and equipment requests.",
        "category_key": "hr_services",
        "sort_order": 1,
        "sla_targets": {
            "response_hours": {"default": 24},
            "resolution_hours": {"default": 72},
        },
    },
]

# ---------------------------------------------------------------------------
# Group definitions (OLA targets keyed by priority level ID)
# ---------------------------------------------------------------------------

GROUPS = [
    {
        "name": "IT Triage Team",
        "description": "First-line incident triage — assess, categorize, and route.",
        "ola_targets": {
            "pickup_hours": {"default": 2, "1": 0.25, "2": 1},
            "closure_hours": {"default": 8, "1": 1, "2": 4},
        },
    },
    {
        "name": "Network Team",
        "description": "L2/L3 network infrastructure support.",
        "ola_targets": {
            "pickup_hours": {"default": 4, "1": 0.5},
            "closure_hours": {"default": 24, "1": 4},
        },
    },
    {
        "name": "Server Team",
        "description": "L2/L3 server and virtualization support.",
        "ola_targets": {
            "pickup_hours": {"default": 4, "1": 0.5},
            "closure_hours": {"default": 24, "1": 4},
        },
    },
    {
        "name": "Application Team",
        "description": "L2/L3 application support and troubleshooting.",
        "ola_targets": {
            "pickup_hours": {"default": 4, "1": 0.5},
            "closure_hours": {"default": 24, "1": 4},
        },
    },
    {
        "name": "QC Verification Team",
        "description": "Post-resolution quality checks with affected users.",
        "ola_targets": {
            "pickup_hours": {"default": 8, "1": 1},
            "closure_hours": {"default": 24, "1": 4},
        },
    },
    {
        "name": "Managers",
        "description": "Department managers with approval authority.",
        "ola_targets": {
            "pickup_hours": {"default": 4, "1": 0.5},
            "closure_hours": {"default": 16, "1": 2},
        },
    },
    {
        "name": "Team Supervisors",
        "description": "Supervisors for affected teams — change sign-off.",
        "ola_targets": {
            "pickup_hours": {"default": 4, "1": 0.5},
            "closure_hours": {"default": 16, "1": 2},
        },
    },
    {
        "name": "Change Advisory Board",
        "description": "CAB — final change approval gate.",
        "ola_targets": {
            "pickup_hours": {"default": 8, "1": 1},
            "closure_hours": {"default": 24, "1": 4},
        },
    },
    {
        "name": "Change Implementation Team",
        "description": "Team that executes approved changes.",
        "ola_targets": {
            "pickup_hours": {"default": 4, "1": 0.5},
            "closure_hours": {"default": 72, "1": 8},
        },
    },
]


# ---------------------------------------------------------------------------
# CMDB Type definitions
# ---------------------------------------------------------------------------

CI_TYPES = [
    {
        "key": "server",
        "name": "Server",
        "icon": "\ud83d\udcbe",
        "description": "Physical or virtual server infrastructure.",
        "field_schema": [
            {"key": "hostname", "label": "Hostname", "type": "string"},
            {"key": "ip_address", "label": "IP Address", "type": "string"},
            {"key": "os", "label": "Operating System", "type": "string"},
            {"key": "cpu_cores", "label": "CPU Cores", "type": "integer"},
            {"key": "ram_gb", "label": "RAM (GB)", "type": "integer"},
            {"key": "datacenter", "label": "Data Center", "type": "string"},
            {"key": "environment", "label": "Environment", "type": "select", "options": ["production", "staging", "development"]},
        ],
    },
    {
        "key": "network_device",
        "name": "Network Device",
        "icon": "\ud83c\udf10",
        "description": "Routers, switches, firewalls, and other network hardware.",
        "field_schema": [
            {"key": "hostname", "label": "Hostname", "type": "string"},
            {"key": "ip_address", "label": "Management IP", "type": "string"},
            {"key": "model", "label": "Model", "type": "string"},
            {"key": "vendor", "label": "Vendor", "type": "string"},
            {"key": "location", "label": "Location", "type": "string"},
            {"key": "firmware_version", "label": "Firmware Version", "type": "string"},
        ],
    },
    {
        "key": "application",
        "name": "Application",
        "icon": "\ud83d\udcf1",
        "description": "Software applications and services.",
        "field_schema": [
            {"key": "app_name", "label": "Application Name", "type": "string"},
            {"key": "version", "label": "Version", "type": "string"},
            {"key": "owner_team", "label": "Owner Team", "type": "string"},
            {"key": "url", "label": "URL", "type": "string"},
            {"key": "tier", "label": "Business Tier", "type": "select", "options": ["Tier 1 - Critical", "Tier 2 - Important", "Tier 3 - Standard"]},
        ],
    },
]

# Sample CI items keyed by type key -> list of items
CI_ITEMS = {
    "server": [
        {"name": "prod-web-01", "status": "active", "ci_data": {"hostname": "prod-web-01.corp.local", "ip_address": "10.0.1.10", "os": "Ubuntu 22.04 LTS", "cpu_cores": 16, "ram_gb": 64, "datacenter": "US-East-1", "environment": "production"}},
        {"name": "prod-db-01", "status": "active", "ci_data": {"hostname": "prod-db-01.corp.local", "ip_address": "10.0.1.20", "os": "RHEL 9", "cpu_cores": 32, "ram_gb": 128, "datacenter": "US-East-1", "environment": "production"}},
        {"name": "staging-app-01", "status": "active", "ci_data": {"hostname": "staging-app-01.corp.local", "ip_address": "10.0.2.10", "os": "Ubuntu 22.04 LTS", "cpu_cores": 8, "ram_gb": 32, "datacenter": "US-East-1", "environment": "staging"}},
    ],
    "network_device": [
        {"name": "core-switch-01", "status": "active", "ci_data": {"hostname": "core-sw-01.corp.local", "ip_address": "10.0.0.1", "model": "Cisco Catalyst 9500", "vendor": "Cisco", "location": "DC-US-East-1 Rack A3", "firmware_version": "17.3.4"}},
        {"name": "edge-firewall-01", "status": "active", "ci_data": {"hostname": "fw-edge-01.corp.local", "ip_address": "10.0.0.254", "model": "Palo Alto PA-3260", "vendor": "Palo Alto Networks", "location": "DC-US-East-1 Rack A1", "firmware_version": "10.2.5"}},
    ],
    "application": [
        {"name": "Customer Portal", "status": "active", "ci_data": {"app_name": "Customer Portal", "version": "3.2.1", "owner_team": "Application Team", "url": "https://portal.example.com", "tier": "Tier 1 - Critical"}},
        {"name": "Internal Wiki", "status": "active", "ci_data": {"app_name": "Internal Wiki", "version": "2.0.0", "owner_team": "IT Operations", "url": "https://wiki.internal.local", "tier": "Tier 3 - Standard"}},
    ],
}


# ---------------------------------------------------------------------------
# KB Article definitions
# ---------------------------------------------------------------------------

KB_ARTICLES = [
    {
        "title": "How to Submit an IT Ticket",
        "slug": "how-to-submit-it-ticket",
        "content": """# How to Submit an IT Ticket

## Getting Help from the IT Service Desk

The IT Service Desk is your first point of contact for all technology-related issues and requests.

### Steps to Submit a Ticket

1. **Navigate to the Offerings page** — select "IT Service Desk" from the service catalog
2. **Choose your request type** — incident (something broken) or change (something new/modified)
3. **Fill in the details**:
   - Describe the issue clearly
   - Select the affected system or application
   - Choose a priority level if known
4. **Submit** — you'll receive a confirmation with your ticket number

### What to Include

- **For incidents**: Error messages, steps to reproduce, when it started, who is affected
- **For changes**: What you want changed, why, any dependencies, preferred timing
- **For access requests**: System name, required permission level, business justification

### Tracking Your Ticket

After submission, you can track progress from "My Submissions" in the portal. You'll receive updates as your ticket moves through triage, assignment, and resolution.""",
        "service_key": "it_service_desk",
        "is_published": True,
        "sort_order": 1,
    },
    {
        "title": "Understanding SLA Priorities",
        "slug": "understanding-sla-priorities",
        "content": """# Understanding SLA Priorities

## Priority Levels

When you submit a request, it's assigned a priority that determines how quickly we respond and resolve it.

| Priority | Response Target | Resolution Target |
|----------|----------------|-------------------|
| Critical (P1) | 30 minutes | 4 hours |
| High (P2) | 1 hour | 8 hours |
| Medium (P3) | 4 hours | 24 hours |
| Low (P4) | 8 hours | 72 hours |

## How Priority is Determined

Priority is based on two factors:

- **Impact**: How many users or systems are affected?
- **Urgency**: How quickly does this need to be resolved?

### Impact Levels
- **High**: Entire department or critical system down
- **Medium**: Single team or non-critical system affected
- **Low**: Individual user, workaround available

### Urgency Levels
- **High**: Business operations stopped
- **Medium**: Degraded performance, no workaround
- **Low**: Minor inconvenience, workaround exists

## Tips for Faster Resolution

1. Provide detailed information when submitting
2. Include screenshots of error messages
3. List steps you've already tried
4. Be available for follow-up questions""",
        "service_key": "it_service_desk",
        "is_published": True,
        "sort_order": 2,
    },
]


# ---------------------------------------------------------------------------
# Demo form definition (references CI types and services)
# ---------------------------------------------------------------------------

DEMO_FORM = {
    "name": "Incident Report",
    "description": "Report an IT incident affecting a system or application. Select the affected CI from the CMDB.",
    "schema": {
        "type": "object",
        "columns": 2,
        "properties": {
            "incident_title": {
                "name": "incident_title",
                "type": "string",
                "title": "Incident Title",
                "description": "Brief summary of the issue",
                "required": True,
                "display_size": "full",
            },
            "affected_ci_type": {
                "name": "affected_ci_type",
                "type": "select",
                "title": "Affected CI Type",
                "description": "Type of configuration item affected",
                "required": True,
                "options": ["Server", "Network Device", "Application"],
                "source": "reference",
                "ref_table": "ci_types",
                "ref_column": "name",
            },
            "affected_ci": {
                "name": "affected_ci",
                "type": "select",
                "title": "Affected System",
                "description": "Specific system or application affected",
                "required": True,
                "options": [],
                "source": "reference",
                "ref_table": "configuration_items",
                "ref_column": "name",
            },
            "service_impact": {
                "name": "service_impact",
                "type": "select",
                "title": "Affected Service",
                "description": "Business service impacted by this incident",
                "required": False,
                "options": [],
                "source": "reference",
                "ref_table": "services",
                "ref_column": "name",
            },
            "priority": {
                "name": "priority",
                "type": "select",
                "title": "Priority",
                "description": "Select the urgency level",
                "required": True,
                "options": ["Critical", "High", "Medium", "Low"],
            },
            "description": {
                "name": "description",
                "type": "textarea",
                "title": "Detailed Description",
                "description": "Describe what happened, when it started, and who is affected",
                "required": True,
                "display_size": "full",
                "data_size": "long",
            },
            "error_message": {
                "name": "error_message",
                "type": "textarea",
                "title": "Error Messages",
                "description": "Copy any error messages or logs here",
                "required": False,
                "display_size": "full",
                "data_size": "medium",
            },
            "workaround_tried": {
                "name": "workaround_tried",
                "type": "boolean",
                "title": "Workaround Available?",
                "description": "Is there a temporary workaround in place?",
                "required": False,
            },
        },
        "required": ["incident_title", "affected_ci_type", "affected_ci", "priority", "description"],
    },
    "environment": "test",
    "is_published": True,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def seed_incident_change_demo_data(
    db: AsyncSession,
) -> Dict[str, int]:
    """Create demo categories, services, and groups idempotently.

    Returns a mapping of group name -> group ID so the workflow installer
    can resolve ``assigned_group_id`` references in step definitions.
    """
    category_ids = await _seed_categories(db)
    service_ids = await _seed_services(db, category_ids)
    group_ids = await _seed_groups(db)

    logger.info(
        "Demo data seeded — categories=%s, services=%s, groups=%s",
        list(category_ids.values()),
        list(service_ids.values()),
        group_ids,
    )
    return group_ids


async def seed_cmdb_demo_data(db: AsyncSession) -> Dict[str, int]:
    """Seed CMDB types and sample items idempotently.

    Returns {type_key: type_id} mapping.
    """
    result: Dict[str, int] = {}
    for ci_type_def in CI_TYPES:
        from app.models.cmdb import CIType
        stmt = select(CIType).where(CIType.key == ci_type_def["key"])
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            result[ci_type_def["key"]] = existing.id
            continue

        ci_type = CIType(
            name=ci_type_def["name"],
            key=ci_type_def["key"],
            icon=ci_type_def.get("icon", ""),
            description=ci_type_def.get("description", ""),
            field_schema=ci_type_def.get("field_schema", []),
            is_active=True,
        )
        db.add(ci_type)
        await db.flush()
        result[ci_type_def["key"]] = ci_type.id
        logger.info("Created CI type: %s (id=%d)", ci_type.name, ci_type.id)

    # Seed sample CI items
    for type_key, items in CI_ITEMS.items():
        type_id = result.get(type_key)
        if not type_id:
            continue
        for item_def in items:
            from app.models.cmdb import ConfigurationItem
            stmt = select(ConfigurationItem).where(
                ConfigurationItem.type_id == type_id,
                ConfigurationItem.name == item_def["name"],
            )
            existing = (await db.execute(stmt)).scalar_one_or_none()
            if existing:
                continue

            ci = ConfigurationItem(
                type_id=type_id,
                name=item_def["name"],
                status=item_def.get("status", "active"),
                ci_data=item_def.get("ci_data", {}),
                is_active=True,
            )
            db.add(ci)
            await db.flush()
            logger.info("Created CI: %s (type=%s, id=%d)", ci.name, type_key, ci.id)

    return result


async def seed_kb_demo_data(db: AsyncSession, service_ids: Dict[str, int]) -> int:
    """Seed KB articles idempotently. Returns count of articles created."""
    created = 0
    for article_def in KB_ARTICLES:
        from app.models.services import KnowledgeBaseArticle
        stmt = select(KnowledgeBaseArticle).where(
            KnowledgeBaseArticle.slug == article_def["slug"]
        )
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            continue

        svc_key = article_def.get("service_key")
        service_id = service_ids.get(svc_key) if svc_key else None

        article = KnowledgeBaseArticle(
            title=article_def["title"],
            slug=article_def["slug"],
            content=article_def["content"],
            service_id=service_id,
            is_published=article_def.get("is_published", True),
            sort_order=article_def.get("sort_order", 0),
        )
        db.add(article)
        await db.flush()
        created += 1
        logger.info("Created KB article: %s (id=%d)", article.title, article.id)

    return created


async def seed_demo_form(db: AsyncSession) -> Optional[int]:
    """Seed the demo Incident Report form idempotently. Returns form ID or None."""
    from app.models.forms import Form
    stmt = select(Form).where(Form.name == DEMO_FORM["name"])
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        return existing.id

    form = Form(
        name=DEMO_FORM["name"],
        description=DEMO_FORM["description"],
        schema_json=DEMO_FORM["schema"],
        version=1,
        environment=DEMO_FORM.get("environment", "test"),
        is_published=DEMO_FORM.get("is_published", False),
        is_active=True,
    )
    db.add(form)
    await db.flush()
    logger.info("Created demo form: %s (id=%d)", form.name, form.id)
    return form.id


async def seed_all_demo_data(db: AsyncSession) -> Dict[str, any]:
    """Seed all demo data: categories, services, groups, CMDB, KB articles, and forms."""
    category_ids = await _seed_categories(db)
    service_ids = await _seed_services(db, category_ids)
    group_ids = await _seed_groups(db)
    ci_type_ids = await seed_cmdb_demo_data(db)
    kb_count = await seed_kb_demo_data(db, service_ids)
    form_id = await seed_demo_form(db)

    return {
        "categories": category_ids,
        "services": service_ids,
        "groups": group_ids,
        "ci_types": ci_type_ids,
        "kb_articles_created": kb_count,
        "demo_form_id": form_id,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _seed_categories(db: AsyncSession) -> Dict[str, int]:
    """Return {key: id} for all categories."""
    result: Dict[str, int] = {}
    for cat_def in CATEGORIES:
        stmt = select(Category).where(Category.key == cat_def["key"])
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            result[cat_def["key"]] = existing.id
            continue

        cat = Category(
            name=cat_def["name"],
            key=cat_def["key"],
            icon=cat_def.get("icon", ""),
            description=cat_def.get("description", ""),
            sort_order=cat_def.get("sort_order", 0),
        )
        db.add(cat)
        await db.flush()
        result[cat_def["key"]] = cat.id
        logger.info("Created category: %s (id=%d)", cat.name, cat.id)

    return result


async def _seed_services(db: AsyncSession, category_ids: Dict[str, int]) -> Dict[str, int]:
    """Return {key: id} for all services."""
    result: Dict[str, int] = {}
    for svc_def in SERVICES:
        stmt = select(Service).where(Service.key == svc_def["key"])
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            result[svc_def["key"]] = existing.id
            continue

        cat_key = svc_def.get("category_key")
        category_id = category_ids.get(cat_key) if cat_key else None

        svc = Service(
            name=svc_def["name"],
            key=svc_def["key"],
            icon=svc_def.get("icon", ""),
            description=svc_def.get("description", ""),
            category_id=category_id,
            sort_order=svc_def.get("sort_order", 0),
            custom_data={"sla_targets": svc_def["sla_targets"]},
        )
        db.add(svc)
        await db.flush()
        result[svc_def["key"]] = svc.id
        logger.info("Created service: %s (id=%d)", svc.name, svc.id)

    return result


async def _seed_groups(db: AsyncSession) -> Dict[str, int]:
    """Return {name: id} for all groups."""
    result: Dict[str, int] = {}
    for grp_def in GROUPS:
        stmt = select(Group).where(Group.name == grp_def["name"])
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            result[grp_def["name"]] = existing.id
            # Ensure OLA targets are set even on existing groups
            if "ola_targets" in grp_def and not (existing.custom_data or {}).get("ola_targets"):
                existing.custom_data = {**(existing.custom_data or {}), "ola_targets": grp_def["ola_targets"]}
            continue

        grp = Group(
            name=grp_def["name"],
            description=grp_def.get("description", ""),
            group_type="internal",
            is_active=True,
            custom_data={"ola_targets": grp_def["ola_targets"]},
        )
        db.add(grp)
        await db.flush()
        result[grp_def["name"]] = grp.id
        logger.info("Created group: %s (id=%d)", grp.name, grp.id)

    return result


async def commit_demo_data(db: AsyncSession) -> None:
    """Commit pending demo data changes. Call after seed_* functions."""
    await db.commit()
    logger.info("Demo data committed")

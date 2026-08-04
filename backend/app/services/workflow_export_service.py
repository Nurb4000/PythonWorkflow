"""
Workflow export service — generates XML and JSON packages for workflow portability.
"""
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from xml.dom import minidom
from xml.etree import ElementTree as ET

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.schemas import Workflow, WorkflowStep, Schedule
from app.models.auth import Group, User
from app.models.forms import Form

logger = logging.getLogger(__name__)


class WorkflowExportService:
    """Export workflows and dependencies to XML or JSON."""

    # Step definition fields that may contain user/group/form/step references
    REF_FIELDS = {
        "assigned_to_user_id", "assigned_group_id", "form_id",
        "next_step_id", "next_step_ids", "data_source_step_id",
        "default_target_step_id"
    }

    async def export_workflow(
        self,
        db: AsyncSession,
        workflow_id: int,
        format: str = "xml",
        include_forms: bool = True,
        include_groups: bool = True,
        include_schedules: bool = True,
        include_permissions: bool = True,
    ) -> Tuple[str, str]:
        """Export a single workflow with dependencies.

        Returns (content, filename).
        """
        # Fetch workflow with steps and allowed_groups
        stmt = (
            select(Workflow)
            .where(Workflow.id == workflow_id)
            .options(selectinload(Workflow.steps), selectinload(Workflow.allowed_groups))
        )
        result = await db.execute(stmt)
        workflow = result.scalar_one_or_none()
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        # Fetch schedules
        schedules: List[Schedule] = []
        if include_schedules:
            sched_stmt = select(Schedule).where(Schedule.workflow_id == workflow_id)
            sched_result = await db.execute(sched_stmt)
            schedules = sched_result.scalars().all()

        # Collect referenced form IDs
        form_ids: Set[int] = set()
        if include_forms and workflow.entry_form_id:
            form_ids.add(workflow.entry_form_id)
        for step in workflow.steps:
            defn = step.definition or {}
            if defn.get("form_id"):
                form_ids.add(defn["form_id"])

        # Fetch forms
        forms: List[Form] = []
        if form_ids:
            form_stmt = select(Form).where(Form.id.in_(form_ids))
            form_result = await db.execute(form_stmt)
            forms = form_result.scalars().all()

        # Collect referenced group IDs (from permissions + step assignments)
        group_ids: Set[int] = set()
        if include_permissions:
            for g in workflow.allowed_groups:
                group_ids.add(g.id)
        for step in workflow.steps:
            defn = step.definition or {}
            if defn.get("assigned_group_id"):
                group_ids.add(defn["assigned_group_id"])

        # Fetch groups
        groups: List[Group] = []
        if group_ids:
            grp_stmt = select(Group).where(Group.id.in_(group_ids))
            grp_result = await db.execute(grp_stmt)
            groups = grp_result.scalars().all()

        # Collect referenced user IDs (for matching on import)
        user_emails: Dict[int, str] = {}
        for step in workflow.steps:
            defn = step.definition or {}
            uid = defn.get("assigned_to_user_id")
            if uid:
                if uid not in user_emails:
                    u_stmt = select(User.email).where(User.id == uid)
                    u_result = await db.execute(u_stmt)
                    email = u_result.scalar_one_or_none()
                    user_emails[uid] = email or ""

        # Build ID mapping: real_id -> symbolic refId
        id_map: Dict[str, Dict[int, str]] = {
            "workflow": {workflow.id: f"wf-{workflow.id}"},
            "step": {},
            "form": {},
            "group": {},
            "user": {}
        }
        for step in workflow.steps:
            id_map["step"][step.id] = f"step-{step.id}"
        for form in forms:
            id_map["form"][form.id] = f"form-{form.id}"
        for group in groups:
            id_map["group"][group.id] = f"group-{group.group_name or group.id}"
        for uid, email in user_emails.items():
            id_map["user"][uid] = f"user-{uid}"

        if format == "xml":
            return self._to_xml(workflow, workflow.steps, schedules, forms, groups, user_emails, id_map, include_forms, include_groups)
        else:
            return self._to_json(workflow, workflow.steps, schedules, forms, groups, user_emails, id_map, include_forms, include_groups)

    def _remap_definition(self, definition: Dict[str, Any], id_map: Dict[str, Dict[int, str]]) -> Dict[str, Any]:
        """Replace real IDs with symbolic refIds in step definition."""
        if not definition:
            return {}
        remapped = dict(definition)

        for field in self.REF_FIELDS:
            if field not in remapped:
                continue
            val = remapped[field]
            if field == "next_step_ids" and isinstance(val, list):
                remapped[field] = [id_map["step"].get(v, str(v)) for v in val]
            elif field == "routes" and isinstance(val, list):
                # routes is a list of {expression, target_step_id}
                remapped[field] = []
                for route in val:
                    r = dict(route)
                    if "target_step_id" in r and r["target_step_id"] is not None:
                        r["target_step_id"] = id_map["step"].get(r["target_step_id"], str(r["target_step_id"]))
                    remapped[field].append(r)
            elif isinstance(val, (int,)) and val:
                # Try step map first, then form, group, user
                if field in ("next_step_id", "data_source_step_id", "default_target_step_id"):
                    remapped[field] = id_map["step"].get(val, str(val))
                elif field == "form_id":
                    remapped[field] = id_map["form"].get(val, str(val))
                elif field == "assigned_group_id":
                    remapped[field] = id_map["group"].get(val, str(val))
                elif field == "assigned_to_user_id":
                    remapped[field] = id_map["user"].get(val, str(val))

        return remapped

    def _to_xml(self, workflow, steps, schedules, forms, groups, user_emails, id_map, include_forms, include_groups) -> Tuple[str, str]:
        root = ET.Element("WorkflowPackage")
        root.set("version", "1.0")
        root.set("exportedAt", datetime.utcnow().isoformat() + "Z")
        root.set("sourceSystem", "PythonWorkflow")

        # Metadata
        meta = ET.SubElement(root, "Metadata")
        ET.SubElement(meta, "Name").text = workflow.name
        ET.SubElement(meta, "Description").text = workflow.description or ""
        ET.SubElement(meta, "ExportedAt").text = root.get("exportedAt", "")

        # Workflow element
        wf = ET.SubElement(root, "Workflow")
        wf.set("name", workflow.name)
        wf.set("isPublished", str(workflow.is_published).lower())
        wf.set("environment", workflow.environment or "test")
        wf.set("isActive", str(workflow.is_active).lower())
        wf.set("version", str(workflow.version))

        # Portal settings
        portal = ET.SubElement(wf, "Portal")
        portal.set("icon", workflow.portal_icon or "")
        portal.set("order", str(workflow.portal_order or 0))
        portal.set("visible", str(workflow.portal_visible).lower())

        # Config (start_step_ids etc)
        config_el = ET.SubElement(wf, "Config")
        config = workflow.config or {}
        if config.get("start_step_ids"):
            remapped_starts = [id_map["step"].get(sid, str(sid)) for sid in config["start_step_ids"]]
            ET.SubElement(config_el, "StartStepIds").text = ",".join(str(s) for s in remapped_starts)

        # Entry form
        if workflow.entry_form_id and include_forms:
            ref = id_map["form"].get(workflow.entry_form_id, str(workflow.entry_form_id))
            entry = ET.SubElement(wf, "EntryForm")
            entry.set("refId", ref)

        # Steps
        steps_el = ET.SubElement(wf, "Steps")
        for step in sorted(steps, key=lambda s: s.position):
            step_el = ET.SubElement(steps_el, "Step")
            step_el.set("id", id_map["step"][step.id])
            step_el.set("type", step.step_type)
            step_el.set("position", str(step.position))
            step_el.set("isEnabled", str(step.is_enabled).lower())

            if step.title:
                ET.SubElement(step_el, "Title").text = step.title
            if step.description:
                ET.SubElement(step_el, "Description").text = step.description
            if step.condition_expr:
                ET.SubElement(step_el, "ConditionExpr").text = step.condition_expr
            if step.max_retries:
                ET.SubElement(step_el, "MaxRetries").text = str(step.max_retries)
            if step.retry_delay_seconds:
                ET.SubElement(step_el, "RetryDelaySeconds").text = str(step.retry_delay_seconds)
            if step.failure_hook_url:
                ET.SubElement(step_el, "FailureHookUrl").text = step.failure_hook_url

            # Definition as JSON (preserves structure)
            remapped_def = self._remap_definition(step.definition or {}, id_map)
            def_el = ET.SubElement(step_el, "Definition")
            def_el.text = json.dumps(remapped_def)

        # Schedules
        if schedules:
            sched_el = ET.SubElement(wf, "Schedules")
            for sched in schedules:
                s = ET.SubElement(sched_el, "Schedule")
                s.set("isEnabled", str(sched.is_enabled).lower())
                ET.SubElement(s, "CronExpression").text = sched.cron_expression

        # Permissions (groups)
        if groups and include_groups:
            perm_el = ET.SubElement(wf, "Permissions")
            for g in workflow.allowed_groups:
                ref = id_map["group"].get(g.id, str(g.id))
                grp = ET.SubElement(perm_el, "Group")
                grp.set("refId", ref)

        # Forms section
        if forms and include_forms:
            forms_section = ET.SubElement(root, "Forms")
            for form in forms:
                f = ET.SubElement(forms_section, "Form")
                f.set("id", id_map["form"][form.id])
                f.set("name", form.name)
                f.set("isPublished", str(form.is_published).lower())
                f.set("environment", form.environment or "test")
                if form.description:
                    ET.SubElement(f, "Description").text = form.description
                schema_el = ET.SubElement(f, "Schema")
                schema_el.text = json.dumps(form.schema_json or {})

        # Groups section
        if groups and include_groups:
            groups_section = ET.SubElement(root, "Groups")
            for g in groups:
                grp = ET.SubElement(groups_section, "Group")
                grp.set("id", id_map["group"][g.id])
                grp.set("name", g.name)
                grp.set("groupType", g.group_type or "internal")
                grp.set("isActive", str(g.is_active).lower())
                if g.description:
                    ET.SubElement(grp, "Description").text = g.description

        # Pretty-print XML
        rough_string = ET.tostring(root, encoding="unicode")
        parsed = minidom.parseString(rough_string)
        xml_output = parsed.toprettyxml(indent="  ", encoding=None)

        filename = f"workflow-{workflow.name.lower().replace(' ', '-')}-{workflow.id}.xml"
        return xml_output, filename

    def _to_json(self, workflow, steps, schedules, forms, groups, user_emails, id_map, include_forms, include_groups) -> Tuple[str, str]:
        data: Dict[str, Any] = {
            "version": "1.0",
            "exportedAt": datetime.utcnow().isoformat() + "Z",
            "sourceSystem": "PythonWorkflow",
            "metadata": {
                "name": workflow.name,
                "description": workflow.description or "",
            },
            "workflow": {
                "name": workflow.name,
                "isPublished": workflow.is_published,
                "environment": workflow.environment or "test",
                "isActive": workflow.is_active,
                "version": workflow.version,
                "portal": {
                    "icon": workflow.portal_icon or "",
                    "order": workflow.portal_order or 0,
                    "visible": workflow.portal_visible,
                },
                "config": workflow.config or {},
            },
            "steps": [],
            "schedules": [],
        }

        # Remap config start_step_ids
        if workflow.config and workflow.config.get("start_step_ids"):
            data["workflow"]["config"]["start_step_ids"] = [
                id_map["step"].get(sid, sid) for sid in workflow.config["start_step_ids"]
            ]

        if workflow.entry_form_id and include_forms:
            data["workflow"]["entryFormRefId"] = id_map["form"].get(workflow.entry_form_id, workflow.entry_form_id)

        for step in sorted(steps, key=lambda s: s.position):
            remapped_def = self._remap_definition(step.definition or {}, id_map)
            data["steps"].append({
                "refId": id_map["step"][step.id],
                "type": step.step_type,
                "position": step.position,
                "isEnabled": step.is_enabled,
                "title": step.title or "",
                "description": step.description or "",
                "conditionExpr": step.condition_expr or "",
                "maxRetries": step.max_retries or 0,
                "retryDelaySeconds": step.retry_delay_seconds or 0,
                "failureHookUrl": step.failure_hook_url or "",
                "definition": remapped_def,
            })

        for sched in schedules:
            data["schedules"].append({
                "isEnabled": sched.is_enabled,
                "cronExpression": sched.cron_expression,
            })

        if groups and include_groups:
            data["permissions"] = [
                id_map["group"].get(g.id, g.id) for g in workflow.allowed_groups
            ]

        if forms and include_forms:
            data["forms"] = []
            for form in forms:
                data["forms"].append({
                    "refId": id_map["form"][form.id],
                    "name": form.name,
                    "isPublished": form.is_published,
                    "environment": form.environment or "test",
                    "description": form.description or "",
                    "schema": form.schema_json or {},
                })

        if groups and include_groups:
            data["groups"] = []
            for g in groups:
                data["groups"].append({
                    "refId": id_map["group"][g.id],
                    "name": g.name,
                    "groupType": g.group_type or "internal",
                    "isActive": g.is_active,
                    "description": g.description or "",
                })

        filename = f"workflow-{workflow.name.lower().replace(' ', '-')}-{workflow.id}.json"
        return json.dumps(data, indent=2), filename


workflow_export_service = WorkflowExportService()

"""
Workflow import service — parses XML/JSON packages and creates workflows with dependencies.
"""
import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.schemas import Workflow, WorkflowStep, Schedule
from app.models.auth import Group, User
from app.models.forms import Form

logger = logging.getLogger(__name__)


class ImportResult:
    """Summary of what was created/matched during import."""

    def __init__(self):
        self.workflows_created: List[str] = []
        self.workflows_created_ids: List[int] = []
        self.workflows_skipped: List[str] = []
        self.forms_created: List[str] = []
        self.forms_matched: List[str] = []
        self.groups_created: List[str] = []
        self.groups_matched: List[str] = []
        self.steps_count: int = 0
        self.schedules_count: int = 0
        self.warnings: List[str] = []
        self.errors: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflowsCreated": self.workflows_created,
            "workflowsCreatedIds": self.workflows_created_ids,
            "workflowsSkipped": self.workflows_skipped,
            "formsCreated": self.forms_created,
            "formsMatched": self.forms_matched,
            "groupsCreated": self.groups_created,
            "groupsMatched": self.groups_matched,
            "stepsCount": self.steps_count,
            "schedulesCount": self.schedules_count,
            "warnings": self.warnings,
            "errors": self.errors,
        }


class WorkflowImportService:
    """Import workflows from XML or JSON packages."""

    async def import_workflow(
        self,
        db: AsyncSession,
        content: str,
        filename: str,
        user_id: int,
        options: Dict[str, Any],
    ) -> ImportResult:
        """Import a workflow package.

        Options:
          - environment: target environment (preserve/override)
          - on_conflict: 'copy' | 'skip' | 'overwrite'
          - create_forms: bool — create missing forms
          - create_groups: bool — create missing groups
          - match_users_by_email: bool — try to resolve user refs by email
        """
        result = ImportResult()

        # Detect format
        if filename.endswith(".json") or content.strip().startswith("{"):
            data = self._parse_json(content, result)
        else:
            data = self._parse_xml(content, result)

        if result.errors:
            return result

        # Extract options
        target_env = options.get("environment", "preserve")
        on_conflict = options.get("on_conflict", "copy")
        create_forms = options.get("create_forms", True)
        create_groups = options.get("create_groups", True)
        match_users_by_email = options.get("match_users_by_email", True)

        # Build refId → real ID mappings
        ref_to_id: Dict[str, int] = {}

        # 1. Create/match groups first (referenced by permissions and steps)
        for grp_data in data.get("groups", []):
            grp_name = grp_data["name"]
            existing = await self._find_group_by_name(db, grp_name)
            if existing:
                ref_to_id[grp_data["refId"]] = existing.id
                result.groups_matched.append(grp_name)
            elif create_groups:
                new_grp = Group(
                    name=grp_name,
                    description=grp_data.get("description", ""),
                    group_type=grp_data.get("groupType", "internal"),
                    is_active=grp_data.get("isActive", True),
                )
                db.add(new_grp)
                await db.flush()
                ref_to_id[grp_data["refId"]] = new_grp.id
                result.groups_created.append(grp_name)
            else:
                result.warnings.append(f"Group '{grp_name}' not found and create_groups is disabled")

        # 2. Create/match forms
        for form_data in data.get("forms", []):
            form_name = form_data["name"]
            existing = await self._find_form_by_name(db, form_name)
            if existing:
                ref_to_id[form_data["refId"]] = existing.id
                result.forms_matched.append(form_name)
            elif create_forms:
                new_form = Form(
                    name=form_name,
                    description=form_data.get("description", ""),
                    schema_json=form_data.get("schema", {}),
                    version=1,
                    is_active=True,
                    created_by=user_id,
                    environment=form_data.get("environment", "test"),
                    is_published=False,
                )
                db.add(new_form)
                await db.flush()
                ref_to_id[form_data["refId"]] = new_form.id
                result.forms_created.append(form_name)
            else:
                result.warnings.append(f"Form '{form_name}' not found and create_forms is disabled")

        # 3. Resolve user references by email
        user_ref_map: Dict[str, Optional[int]] = {}
        if match_users_by_email:
            for uid, email in data.get("users", {}).items():
                if email:
                    user = await self._find_user_by_email(db, email)
                    if user:
                        user_ref_map[uid] = user.id
                    else:
                        result.warnings.append(f"User with email '{email}' not found — assignments will be skipped")

        # 4. Create workflow
        wf_data = data["workflow"]
        wf_name = wf_data["name"]

        # Check for existing workflow with same name
        existing_wf = await self._find_workflow_by_name(db, wf_name)
        if existing_wf and on_conflict == "skip":
            result.workflows_skipped.append(wf_name)
            return result

        if existing_wf and on_conflict == "overwrite":
            # Update existing workflow
            new_wf = existing_wf
            new_wf.name = wf_name
            new_wf.description = wf_data.get("description", "")
            new_wf.is_published = False
            new_wf.environment = "test"
            new_wf.is_active = False
            new_wf.version = (new_wf.version or 1) + 1
            new_wf.portal_icon = wf_data.get("portal", {}).get("icon", "")
            new_wf.portal_order = wf_data.get("portal", {}).get("order", 0)
            new_wf.portal_visible = wf_data.get("portal", {}).get("visible", True)
            new_wf.config = wf_data.get("config", {})
            new_wf.created_by = user_id
            # Clean existing steps and schedules before re-creating
            from sqlalchemy import delete as sa_delete
            await db.execute(sa_delete(WorkflowStep).where(WorkflowStep.workflow_id == new_wf.id))
            await db.execute(sa_delete(Schedule).where(Schedule.workflow_id == new_wf.id))
        else:
            # Create new workflow (or copy if name exists)
            final_name = wf_name
            if existing_wf and on_conflict == "copy":
                counter = 1
                while True:
                    final_name = f"{wf_name} (Copy {counter})"
                    check = await self._find_workflow_by_name(db, final_name)
                    if not check:
                        break
                    counter += 1

            new_wf = Workflow(
                name=final_name,
                description=wf_data.get("description", ""),
                version=wf_data.get("version", 1),
                is_active=False,
                created_by=user_id,
                is_published=False,
                environment="test",
                config=wf_data.get("config", {}),
                portal_icon=wf_data.get("portal", {}).get("icon", ""),
                portal_order=wf_data.get("portal", {}).get("order", 0),
                portal_visible=wf_data.get("portal", {}).get("visible", True),
            )
            db.add(new_wf)
            await db.flush()

        # Remap entry_form_id
        entry_ref = wf_data.get("entryFormRefId")
        if entry_ref and entry_ref in ref_to_id:
            new_wf.entry_form_id = ref_to_id[entry_ref]
        elif entry_ref:
            result.warnings.append(f"Entry form ref '{entry_ref}' not resolved")

        # Remap config start_step_ids (they're symbolic refIds, will be remapped after steps are created)
        # We'll handle this after step creation

        # 5. Create steps
        step_ref_to_id: Dict[str, int] = {}
        for step_data in data.get("steps", []):
            definition = step_data.get("definition", {})
            # Remap references in definition
            definition = self._remap_definition_refs(definition, ref_to_id, user_ref_map)

            new_step = WorkflowStep(
                workflow_id=new_wf.id,
                step_type=step_data["type"],
                definition=definition,
                position=step_data.get("position", 0),
                condition_expr=step_data.get("conditionExpr", ""),
                is_enabled=step_data.get("isEnabled", True),
                title=step_data.get("title", ""),
                description=step_data.get("description", ""),
                max_retries=step_data.get("maxRetries", 0),
                retry_delay_seconds=step_data.get("retryDelaySeconds", 0),
                failure_hook_url=step_data.get("failureHookUrl", ""),
            )
            db.add(new_step)
            await db.flush()
            step_ref_to_id[step_data["refId"]] = new_step.id
            result.steps_count += 1

        # 5b. Second pass: remap inter-step references (next_step_ids, routes, etc.)
        for step_data in data.get("steps", []):
            new_step_id = step_ref_to_id.get(step_data["refId"])
            if new_step_id is None:
                continue
            stmt = select(WorkflowStep).where(WorkflowStep.id == new_step_id)
            step_result = await db.execute(stmt)
            saved_step = step_result.scalar_one()
            defn = dict(saved_step.definition or {})
            # Remap next_step_ids
            if "next_step_ids" in defn and isinstance(defn["next_step_ids"], list):
                defn["next_step_ids"] = [
                    step_ref_to_id.get(ref, ref) for ref in defn["next_step_ids"]
                ]
            # Remap single step refs
            for field in ("next_step_id", "data_source_step_id", "default_target_step_id"):
                if field in defn and defn[field]:
                    val = defn[field]
                    if isinstance(val, str) and val in step_ref_to_id:
                        defn[field] = step_ref_to_id[val]
            # Remap routes[].target_step_id
            if "routes" in defn and isinstance(defn["routes"], list):
                for route in defn["routes"]:
                    if "target_step_id" in route and route["target_step_id"]:
                        val = route["target_step_id"]
                        if isinstance(val, str) and val in step_ref_to_id:
                            route["target_step_id"] = step_ref_to_id[val]
                        elif val == "-1":
                            route["target_step_id"] = -1  # END_TARGET sentinel
            # Normalize END_TARGET sentinels from string to int
            if "next_step_ids" in defn and isinstance(defn["next_step_ids"], list):
                defn["next_step_ids"] = [-1 if v == "-1" else v for v in defn["next_step_ids"]]
            for field in ("next_step_id", "default_target_step_id", "data_source_step_id"):
                if field in defn and defn[field] == "-1":
                    defn[field] = -1
            saved_step.definition = defn

        # 6. Remap config start_step_ids using step_ref_to_id
        original_refs = data["workflow"].get("config", {}).get("start_step_ids", [])
        logger.info(f"Import start_step_ids: original_refs={original_refs}, step_ref_to_id={step_ref_to_id}")
        if original_refs:
            remapped_ids = []
            for ref in original_refs:
                if ref in step_ref_to_id:
                    remapped_ids.append(step_ref_to_id[ref])
                elif isinstance(ref, str) and ref.startswith("step-"):
                    for sr, ri in step_ref_to_id.items():
                        if sr == ref:
                            remapped_ids.append(ri)
                            break
            # Ensure config dict exists and has remapped start_step_ids
            if not new_wf.config:
                new_wf.config = {}
            new_wf.config["start_step_ids"] = remapped_ids
            logger.info(f"Import start_step_ids: remapped={remapped_ids}")

        # 7. Create schedules
        for sched_data in data.get("schedules", []):
            new_sched = Schedule(
                workflow_id=new_wf.id,
                cron_expression=sched_data["cronExpression"],
                is_enabled=sched_data.get("isEnabled", True),
            )
            db.add(new_sched)
            result.schedules_count += 1

        # 8. Set up permissions (workflow-group associations)
        perm_group_refs = data.get("permissions", [])
        if perm_group_refs:
            from app.models.auth import workflow_permissions
            from sqlalchemy import delete, insert

            # Clear existing permissions
            await db.execute(delete(workflow_permissions).where(workflow_permissions.c.workflow_id == new_wf.id))

            for ref in perm_group_refs:
                if ref in ref_to_id:
                    gid = ref_to_id[ref]
                    await db.execute(insert(workflow_permissions).values(workflow_id=new_wf.id, group_id=gid))

        await db.commit()
        result.workflows_created.append(new_wf.name)
        result.workflows_created_ids.append(new_wf.id)

        return result

    def _remap_definition_refs(self, definition: Dict[str, Any], ref_to_id: Dict[str, int], user_ref_map: Dict[str, Optional[int]]) -> Dict[str, Any]:
        """Replace symbolic refIds with real database IDs in step definition."""
        if not definition:
            return {}
        remapped = dict(definition)

        # Remap next_step_ids (list of step refIds)
        if "next_step_ids" in remapped and isinstance(remapped["next_step_ids"], list):
            remapped["next_step_ids"] = [
                ref_to_id.get(ref, ref) for ref in remapped["next_step_ids"]
            ]

        # Remap single step refs
        for field in ("next_step_id", "data_source_step_id", "default_target_step_id"):
            if field in remapped and remapped[field]:
                val = remapped[field]
                if isinstance(val, str) and val in ref_to_id:
                    remapped[field] = ref_to_id[val]

        # Remap routes[].target_step_id
        if "routes" in remapped and isinstance(remapped["routes"], list):
            for route in remapped["routes"]:
                if "target_step_id" in route and route["target_step_id"]:
                    val = route["target_step_id"]
                    if isinstance(val, str) and val in ref_to_id:
                        route["target_step_id"] = ref_to_id[val]

        # Remap form_id
        if "form_id" in remapped and remapped["form_id"]:
            val = remapped["form_id"]
            if isinstance(val, str) and val in ref_to_id:
                remapped["form_id"] = ref_to_id[val]

        # Remap assigned_group_id
        if "assigned_group_id" in remapped and remapped["assigned_group_id"]:
            val = remapped["assigned_group_id"]
            if isinstance(val, str) and val in ref_to_id:
                remapped["assigned_group_id"] = ref_to_id[val]

        # Remap assigned_to_user_id (by email match)
        if "assigned_to_user_id" in remapped and remapped["assigned_to_user_id"]:
            val = remapped["assigned_to_user_id"]
            if isinstance(val, str) and val in user_ref_map:
                uid = user_ref_map[val]
                if uid:
                    remapped["assigned_to_user_id"] = uid
                else:
                    del remapped["assigned_to_user_id"]

        return remapped

    def _parse_xml(self, content: str, result: ImportResult) -> Dict[str, Any]:
        """Parse XML workflow package into structured dict."""
        from xml.etree import ElementTree as ET

        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            result.errors.append(f"Invalid XML: {e}")
            return {}

        data: Dict[str, Any] = {
            "workflow": {},
            "steps": [],
            "schedules": [],
            "forms": [],
            "groups": [],
            "permissions": [],
            "users": {},
        }

        # Parse workflow element
        wf_el = root.find("Workflow")
        if wf_el is None:
            result.errors.append("No <Workflow> element found in XML")
            return {}

        data["workflow"]["name"] = wf_el.get("name", "")
        data["workflow"]["isPublished"] = wf_el.get("isPublished", "false") == "true"
        data["workflow"]["environment"] = wf_el.get("environment", "test")
        data["workflow"]["isActive"] = wf_el.get("isActive", "true") == "true"
        data["workflow"]["version"] = int(wf_el.get("version", "1"))

        # Portal settings
        portal_el = wf_el.find("Portal")
        if portal_el is not None:
            data["workflow"]["portal"] = {
                "icon": portal_el.get("icon", ""),
                "order": int(portal_el.get("order", "0")),
                "visible": portal_el.get("visible", "true") == "true",
            }

        # Config
        config_el = wf_el.find("Config")
        if config_el is not None:
            start_ids_el = config_el.find("StartStepIds")
            if start_ids_el is not None and start_ids_el.text:
                data["workflow"]["config"] = {
                    "start_step_ids": [s.strip() for s in start_ids_el.text.split(",") if s.strip()]
                }

        # Entry form
        entry_el = wf_el.find("EntryForm")
        if entry_el is not None:
            data["workflow"]["entryFormRefId"] = entry_el.get("refId")

        # Steps
        steps_el = wf_el.find("Steps")
        if steps_el is not None:
            for step_el in steps_el.findall("Step"):
                ref_id = step_el.get("id", "")
                step_data = {
                    "refId": ref_id,
                    "type": step_el.get("type", ""),
                    "position": int(step_el.get("position", "0")),
                    "isEnabled": step_el.get("isEnabled", "true") == "true",
                    "title": (step_el.findtext("Title") or ""),
                    "description": (step_el.findtext("Description") or ""),
                    "conditionExpr": (step_el.findtext("ConditionExpr") or ""),
                    "maxRetries": int(step_el.findtext("MaxRetries") or "0"),
                    "retryDelaySeconds": int(step_el.findtext("RetryDelaySeconds") or "0"),
                    "failureHookUrl": (step_el.findtext("FailureHookUrl") or ""),
                }

                # Parse definition JSON
                def_el = step_el.find("Definition")
                if def_el is not None and def_el.text:
                    try:
                        step_data["definition"] = json.loads(def_el.text)
                    except json.JSONDecodeError:
                        step_data["definition"] = {}
                else:
                    step_data["definition"] = {}

                data["steps"].append(step_data)

        # Schedules
        sched_el = wf_el.find("Schedules")
        if sched_el is not None:
            for s in sched_el.findall("Schedule"):
                cron_el = s.find("CronExpression")
                data["schedules"].append({
                    "isEnabled": s.get("isEnabled", "true") == "true",
                    "cronExpression": cron_el.text if cron_el is not None else "",
                })

        # Permissions
        perm_el = wf_el.find("Permissions")
        if perm_el is not None:
            for g in perm_el.findall("Group"):
                data["permissions"].append(g.get("refId", ""))

        # Forms
        forms_section = root.find("Forms")
        if forms_section is not None:
            for f in forms_section.findall("Form"):
                ref_id = f.get("id", "")
                schema_el = f.find("Schema")
                form_data = {
                    "refId": ref_id,
                    "name": f.get("name", ""),
                    "isPublished": f.get("isPublished", "false") == "true",
                    "environment": f.get("environment", "test"),
                    "description": (f.findtext("Description") or ""),
                    "schema": json.loads(schema_el.text) if schema_el is not None and schema_el.text else {},
                }
                data["forms"].append(form_data)

        # Groups
        groups_section = root.find("Groups")
        if groups_section is not None:
            for g in groups_section.findall("Group"):
                ref_id = g.get("id", "")
                grp_data = {
                    "refId": ref_id,
                    "name": g.get("name", ""),
                    "groupType": g.get("groupType", "internal"),
                    "isActive": g.get("isActive", "true") == "true",
                    "description": (g.findtext("Description") or ""),
                }
                data["groups"].append(grp_data)

        return data

    def _parse_json(self, content: str, result: ImportResult) -> Dict[str, Any]:
        """Parse JSON workflow package."""
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            result.errors.append(f"Invalid JSON: {e}")
            return {}

        # Normalize JSON structure to match internal format
        if "workflow" not in data:
            result.errors.append("Missing 'workflow' key in JSON package")
            return {}

        wf = data["workflow"]
        normalized: Dict[str, Any] = {
            "workflow": {
                "name": wf.get("name", ""),
                "isPublished": wf.get("isPublished", False),
                "environment": wf.get("environment", "test"),
                "isActive": wf.get("isActive", True),
                "version": wf.get("version", 1),
                "portal": wf.get("portal", {}),
                "config": wf.get("config", {}),
                "entryFormRefId": wf.get("entryFormRefId"),
            },
            "steps": data.get("steps", []),
            "schedules": data.get("schedules", []),
            "forms": data.get("forms", []),
            "groups": data.get("groups", []),
            "permissions": data.get("permissions", []),
            "users": data.get("users", {}),
        }

        return normalized

    async def _find_group_by_name(self, db: AsyncSession, name: str) -> Optional[Group]:
        stmt = select(Group).where(Group.name == name)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _find_form_by_name(self, db: AsyncSession, name: str) -> Optional[Form]:
        stmt = select(Form).where(Form.name == name)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _find_user_by_email(self, db: AsyncSession, email: str) -> Optional[User]:
        stmt = select(User).where(User.email == email)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _find_workflow_by_name(self, db: AsyncSession, name: str) -> Optional[Workflow]:
        stmt = select(Workflow).where(Workflow.name == name)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def duplicate_workflow(
        self,
        db: AsyncSession,
        workflow_id: int,
        user_id: int,
        new_name: Optional[str] = None,
    ) -> Workflow:
        """Duplicate a workflow within the same system."""
        stmt = (
            select(Workflow)
            .where(Workflow.id == workflow_id)
            .options(selectinload(Workflow.steps), selectinload(Workflow.allowed_groups))
        )
        result = await db.execute(stmt)
        source = result.scalar_one_or_none()
        if not source:
            raise ValueError(f"Workflow {workflow_id} not found")

        # Generate unique name
        dup_name = new_name or f"{source.name} (Copy)"
        counter = 1
        while True:
            existing = await self._find_workflow_by_name(db, dup_name)
            if not existing:
                break
            dup_name = f"{source.name} (Copy {counter})"
            counter += 1

        # Create new workflow
        new_wf = Workflow(
            name=dup_name,
            description=source.description or "",
            version=source.version or 1,
            is_active=source.is_active,
            created_by=user_id,
            is_published=False,  # Duplicates start as draft
            environment=source.environment or "test",
            config=dict(source.config) if source.config else {},
            portal_icon=source.portal_icon or "",
            portal_order=source.portal_order or 0,
            portal_visible=source.portal_visible,
        )
        db.add(new_wf)
        await db.flush()

        # Copy steps (remap internal step references later)
        old_to_new_step: Dict[int, int] = {}
        for step in source.steps:
            new_step = WorkflowStep(
                workflow_id=new_wf.id,
                step_type=step.step_type,
                definition=dict(step.definition) if step.definition else {},
                position=step.position,
                condition_expr=step.condition_expr or "",
                is_enabled=step.is_enabled,
                title=step.title or "",
                description=step.description or "",
                max_retries=step.max_retries or 0,
                retry_delay_seconds=step.retry_delay_seconds or 0,
                failure_hook_url=step.failure_hook_url or "",
            )
            db.add(new_step)
            await db.flush()
            old_to_new_step[step.id] = new_step.id

        # Remap step references in definitions
        for new_step_id in old_to_new_step.values():
            stmt = select(WorkflowStep).where(WorkflowStep.id == new_step_id)
            result = await db.execute(stmt)
            new_step = result.scalar_one()
            defn = new_step.definition or {}

            # Remap next_step_ids
            if "next_step_ids" in defn and isinstance(defn["next_step_ids"], list):
                defn["next_step_ids"] = [old_to_new_step.get(sid, sid) for sid in defn["next_step_ids"]]
            if "next_step_id" in defn and defn["next_step_id"]:
                defn["next_step_id"] = old_to_new_step.get(defn["next_step_id"], defn["next_step_id"])
            if "data_source_step_id" in defn and defn["data_source_step_id"]:
                defn["data_source_step_id"] = old_to_new_step.get(defn["data_source_step_id"], defn["data_source_step_id"])
            if "default_target_step_id" in defn and defn["default_target_step_id"]:
                defn["default_target_step_id"] = old_to_new_step.get(defn["default_target_step_id"], defn["default_target_step_id"])

            # Remap routes[].target_step_id
            if "routes" in defn and isinstance(defn["routes"], list):
                for route in defn["routes"]:
                    if "target_step_id" in route and route["target_step_id"]:
                        route["target_step_id"] = old_to_new_step.get(route["target_step_id"], route["target_step_id"])

            new_step.definition = defn

        # Remap config start_step_ids
        if new_wf.config and new_wf.config.get("start_step_ids"):
            new_wf.config["start_step_ids"] = [
                old_to_new_step.get(sid, sid) for sid in new_wf.config["start_step_ids"]
            ]

        # Copy schedules
        sched_stmt = select(Schedule).where(Schedule.workflow_id == source.id)
        sched_result = await db.execute(sched_stmt)
        for sched in sched_result.scalars().all():
            new_sched = Schedule(
                workflow_id=new_wf.id,
                cron_expression=sched.cron_expression,
                is_enabled=sched.is_enabled,
            )
            db.add(new_sched)

        # Copy permissions (group associations)
        from app.models.auth import workflow_permissions
        from sqlalchemy import insert
        for group in source.allowed_groups:
            await db.execute(
                insert(workflow_permissions).values(workflow_id=new_wf.id, group_id=group.id)
            )

        await db.commit()
        await db.refresh(new_wf)

        logger.info(f"Duplicated workflow '{source.name}' as '{dup_name}'")
        return new_wf


workflow_import_service = WorkflowImportService()

"""
Core workflow engine for executing workflows and steps
"""
import asyncio
import ast
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, func

from app.core.database import async_session_factory
from app.models.schemas import Workflow, WorkflowStep, WorkflowRun, StepInstance, Task
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate, WorkflowRunCreate
from app.services.email_service import notify_admin
from app.services.interpolation import ReferenceContext, interpolate, context_has_templates
from app.services.workflow_version_service import snapshot_workflow
from app.services.tenant_scoping import resolve_creation_tenant_id
from app.models.auth import User

logger = logging.getLogger(__name__)


class _RunCtx:
    """In-memory coordination state shared across concurrent DAG branch tasks.

    With true parallel execution each branch runs on its *own* ``AsyncSession``, so the
    ORM ``WorkflowRun`` object can no longer be shared (each session has its own identity
    map and updates in one session are not visible in another without a refresh). This
    lightweight stand-in holds exactly the attributes the step-execution helpers read and
    write:

    * ``input_data`` — the accumulated run input. Merging a step's output here is what lets
      a converging (fan-in) step see every predecessor's outputs.
    * ``status`` / ``error_message`` / ``completed_at`` — run-level coordination for
      timeout, per-step failure, and human-task pause.

    It is safe to mutate from multiple coroutines because asyncio is single-threaded and
    every mutation below is a synchronous read-modify-write (no ``await`` in between), so
    two branches can never interleave a partial update. The live engine writes the final
    values back onto the ORM ``run`` before the caller's finalize step reads it.
    """

    __slots__ = (
        "id", "input_data", "status", "error_message", "max_retries",
        "timeout_seconds", "started_at", "completed_at", "priority",
        "tenant_id", "failure_hooks",
    )

    def __init__(self, run: WorkflowRun):
        self.id = run.id
        self.input_data = dict(run.input_data or {})
        self.status = run.status
        self.error_message = run.error_message
        self.max_retries = run.max_retries
        self.timeout_seconds = run.timeout_seconds
        self.started_at = run.started_at
        self.completed_at = run.completed_at
        self.priority = getattr(run, "priority", None)
        self.tenant_id = run.tenant_id
        self.failure_hooks = list(getattr(run, "failure_hooks", None) or [])


class WorkflowEngine:
    """Main workflow execution engine"""
    
    def __init__(self):
        self.step_executors = {}
        self._register_default_executors()
    
    def _register_default_executors(self):
        """Register built-in step executors"""
        from app.services.step_executors import (
            APICallExecutor,
            DatabaseQueryExecutor,
            EmailExecutor,
            ConditionExecutor,
            DelayExecutor,
            FormExecutor,
            WebhookExecutor,
            CustomCodeExecutor,
            CalculationExecutor,
            ReportExecutor,
            ReadonlyFormExecutor,
            AIConditionExecutor,
            ProgrammableDelayExecutor,
            CmdbLookupExecutor,
            CmdbUpdateExecutor,
            SubWorkflowExecutor,
            LoopExecutor,
        )

        self.step_executors = {
            "api_call": APICallExecutor(),
            "database_query": DatabaseQueryExecutor(),
            "email": EmailExecutor(),
            "condition": ConditionExecutor(),
            "delay": DelayExecutor(),
            "form": FormExecutor(),
            "webhook": WebhookExecutor(),
            "custom_code": CustomCodeExecutor(),
            "calculation": CalculationExecutor(),  # P5.1
            "report": ReportExecutor(),  # P5.3
            "readonly_form": ReadonlyFormExecutor(),  # P5.3
            "ai_condition": AIConditionExecutor(),  # P5.2
            "programmable_delay": ProgrammableDelayExecutor(),  # P5.5
            "cmdb_lookup": CmdbLookupExecutor(),  # CMDB Phase 3
            "cmdb_update": CmdbUpdateExecutor(),  # CMDB Phase 3
            "sub_workflow": SubWorkflowExecutor(),  # B3: sync sub-workflow
            "loop": LoopExecutor(),  # M1: iterate a collection over an inner step
        }
    
    def validate_input_refs(self, steps: List[Dict[str, Any]], entry_form_schema: Optional[Dict] = None) -> List[str]:
        """B1: Validate $input.* references in steps against entry form schema.
        
        Returns list of warning/error messages. Empty list means valid.
        """
        import re
        warnings = []
        
        # Build set of valid input fields from entry form schema
        valid_fields = set()
        if entry_form_schema:
            properties = entry_form_schema.get("properties", {})
            for field_name in properties:
                valid_fields.add(field_name)
        
        # Extract all $input.* references from steps
        input_pattern = re.compile(r'\$input\.(\w+)')
        referenced_fields = set()
        
        for i, step in enumerate(steps):
            step_def = step.get("definition", {})
            step_json = str(step_def)
            
            # Find all $input.* references
            matches = input_pattern.findall(step_json)
            for field in matches:
                referenced_fields.add(field)
                
                # Check if field exists in entry form schema
                if entry_form_schema and field not in valid_fields:
                    warnings.append(
                        f"Step {i+1} ({step.get('title', step.get('step_type', '?'))}): "
                        f"$input.{field} references a field not in the entry form schema"
                    )
        
        # Warn about unreferenced form fields
        if entry_form_schema and valid_fields:
            unused = valid_fields - referenced_fields
            if unused:
                warnings.append(
                    f"Entry form has {len(unused)} field(s) not referenced by any step: "
                    f"{', '.join(sorted(unused)[:5])}{'...' if len(unused) > 5 else ''}"
                )
        
        return warnings
    
    async def create_workflow(self, db: AsyncSession, workflow_data: WorkflowCreate,
                              created_by: Optional[int] = None,
                              allowed_group_ids: Optional[List[int]] = None) -> Workflow:
        """Create a new workflow"""
        # A1: naming discipline — reject exact case-insensitive duplicates
        norm_name = workflow_data.name.strip()
        if not norm_name:
            raise ValueError("Workflow name cannot be empty")
        if len(norm_name) > 80:
            raise ValueError("Workflow name must be 80 characters or fewer")
        stmt = select(Workflow.id).where(
            func.lower(Workflow.name) == func.lower(norm_name),
            Workflow.is_active == True
        )
        result = await db.execute(stmt)
        if result.scalar() is not None:
            raise ValueError(f"Workflow with name '{norm_name}' already exists (case-insensitive)")
        
        # B1: validate input refs
        entry_form_schema = None
        if workflow_data.entry_form_id:
            from app.models.forms import Form
            form_stmt = select(Form).where(Form.id == workflow_data.entry_form_id)
            form_result = await db.execute(form_stmt)
            form = form_result.scalar_one_or_none()
            if form:
                import json
                entry_form_schema = json.loads(form.schema_json) if isinstance(form.schema_json, str) else form.schema_json
        
        validation_warnings = self.validate_input_refs(workflow_data.steps or [], entry_form_schema)
        if validation_warnings:
            logger.warning(f"Workflow '{norm_name}' has input validation warnings: {validation_warnings}")

        # Multi-tenancy (§3.1): assign the creating user's tenant (or the seeded
        # default) so the NOT NULL tenant_id column enforced by the content migration
        # is satisfied and the workflow is scoped to that tenant on read.
        # Always run the query so we get a real Result object; when ``created_by``
        # is None we drop the WHERE clause. ``.scalar_one_or_none()`` then safely
        # yields ``None`` (no matching user). The old code stored ``None`` directly
        # for the no-creator case and then called ``.scalar_one_or_none()`` on that
        # ``None``, crashing every workflow created without an explicit creator
        # (e.g. all engine/graph tests).
        user_stmt = select(User).where(User.id == created_by) \
            if created_by is not None else select(User)
        creator_result = await db.execute(user_stmt)
        tenant_id = await resolve_creation_tenant_id(db, creator_result.scalar_one_or_none())

        workflow = Workflow(
            name=norm_name,
            description=workflow_data.description,
            version=1,
            config=workflow_data.config or {},
            portal_icon=workflow_data.portal_icon,
            portal_order=workflow_data.portal_order,
            portal_visible=workflow_data.portal_visible,
            entry_form_id=workflow_data.entry_form_id,
            created_by=created_by,
            owner_user_id=workflow_data.owner_user_id or created_by,
            tags=workflow_data.tags or [],
            tenant_id=tenant_id
        )
        db.add(workflow)
        await db.flush()

        # Store input-validation warnings in config for UI display (non-blocking).
        # Assigned after `workflow` is constructed — previously referenced before
        # assignment, raising NameError whenever a workflow had validation warnings.
        if validation_warnings:
            workflow.config = workflow.config or {}
            workflow.config["input_validation_warnings"] = validation_warnings

        # Assign permitted groups (direct association-table insert avoids async lazy-load)
        if allowed_group_ids:
            from sqlalchemy import insert
            from app.models.auth import Group, workflow_permissions
            stmt = select(Group).where(Group.id.in_(allowed_group_ids))
            result = await db.execute(stmt)
            groups = result.scalars().all()
            await db.execute(
                insert(workflow_permissions),
                [{"workflow_id": workflow.id, "group_id": g.id} for g in groups]
            )
        
        # Create steps
        for i, step_data in enumerate(workflow_data.steps):
            step = WorkflowStep(
                workflow_id=workflow.id,
                step_type=step_data["step_type"],
                definition=step_data.get("definition", {}),
                position=i,
                condition_expr=step_data.get("condition_expr", ""),
                is_enabled=step_data.get("is_enabled", True),
                title=step_data.get("title", ""),
                description=step_data.get("description", ""),
                tenant_id=tenant_id
            )
            db.add(step)

        # §2.4: capture the initial version-1 snapshot. The snapshot query's autoflush
        # flushes the just-added steps so they are included in the stored definition.
        await snapshot_workflow(db, workflow, version_number=1, created_by=created_by)

        await db.commit()
        await db.refresh(workflow, attribute_names=["steps"])
        return workflow

    async def update_workflow(self, db: AsyncSession, workflow_id: int, workflow_data: WorkflowUpdate,
                              created_by: Optional[int] = None) -> Optional[Workflow]:
        """Update an existing workflow"""
        stmt = select(Workflow).where(Workflow.id == workflow_id)
        result = await db.execute(stmt)
        workflow = result.scalar_one_or_none()
        
        if not workflow:
            return None
        
        if workflow_data.name is not None:
            norm_name = workflow_data.name.strip()
            if not norm_name:
                raise ValueError("Workflow name cannot be empty")
            if len(norm_name) > 80:
                raise ValueError("Workflow name must be 80 characters or fewer")
            # Check for duplicates excluding this workflow
            stmt_dup = select(Workflow.id).where(
                func.lower(Workflow.name) == func.lower(norm_name),
                Workflow.id != workflow_id,
                Workflow.is_active == True
            )
            result_dup = await db.execute(stmt_dup)
            if result_dup.scalar() is not None:
                raise ValueError(f"Workflow with name '{norm_name}' already exists (case-insensitive)")
            workflow.name = norm_name
        if workflow_data.description is not None:
            workflow.description = workflow_data.description
        if workflow_data.is_active is not None:
            workflow.is_active = workflow_data.is_active
        if workflow_data.is_published is not None:
            workflow.is_published = workflow_data.is_published
        if workflow_data.environment is not None:
            workflow.environment = workflow_data.environment
        if workflow_data.config is not None:
            workflow.config = workflow_data.config
        if workflow_data.portal_icon is not None:
            workflow.portal_icon = workflow_data.portal_icon
        if workflow_data.portal_order is not None:
            workflow.portal_order = workflow_data.portal_order
        if workflow_data.portal_visible is not None:
            workflow.portal_visible = workflow_data.portal_visible
        if workflow_data.portal_link_url is not None:
            current = dict(workflow.config) if workflow.config else {}
            if workflow_data.portal_link_url:
                current["portal_link_url"] = workflow_data.portal_link_url
            else:
                current.pop("portal_link_url", None)
            workflow.config = current
        
        # P3.3: Entry form — only update if explicitly provided in request
        if "entry_form_id" in workflow_data.model_fields_set:
            workflow.entry_form_id = workflow_data.entry_form_id

        # SERVICE_MANAGEMENT_PLAN Phase 1.4: service association
        if "service_id" in workflow_data.model_fields_set:
            workflow.service_id = workflow_data.service_id
        
        # P7: Manual version increment
        if workflow_data.manual_version_increment:
            workflow.version += 1
        
        # A3: owner and tags
        if workflow_data.owner_user_id is not None:
            workflow.owner_user_id = workflow_data.owner_user_id
        if workflow_data.tags is not None:
            workflow.tags = workflow_data.tags
        
        # E1: deprecation
        if workflow_data.is_deprecated is not None:
            workflow.is_deprecated = workflow_data.is_deprecated
            if workflow_data.is_deprecated:
                workflow.deprecated_at = datetime.now(timezone.utc)
                workflow.deprecated_by_id = created_by
            else:
                workflow.deprecated_at = None
                workflow.deprecated_by_id = None
        if workflow_data.suggested_replacement_id is not None:
            workflow.suggested_replacement_id = workflow_data.suggested_replacement_id
        
        # M15 fix: validate $input.* references on update (same as create).
        # Previously only create_workflow called validate_input_refs.
        if workflow_data.steps is not None:
            entry_form_schema = None
            if workflow.entry_form_id:
                from app.models.forms import Form
                form_stmt = select(Form).where(Form.id == workflow.entry_form_id)
                form_result = await db.execute(form_stmt)
                form = form_result.scalar_one_or_none()
                if form:
                    import json
                    entry_form_schema = (
                        json.loads(form.schema_json)
                        if isinstance(form.schema_json, str)
                        else form.schema_json
                    )

            validation_warnings = self.validate_input_refs(
                workflow_data.steps or [], entry_form_schema
            )
            if validation_warnings:
                logger.warning(
                    f"Workflow '{workflow.name}' update has input validation warnings: "
                    f"{validation_warnings}"
                )
                workflow.config = workflow.config or {}
                workflow.config["input_validation_warnings"] = validation_warnings

            # Delete existing steps
            stmt = select(WorkflowStep).where(WorkflowStep.workflow_id == workflow_id)
            result = await db.execute(stmt)
            existing_steps = result.scalars().all()
            
            for step in existing_steps:
                await db.delete(step)
            
            # Create new steps
            for i, step_data in enumerate(workflow_data.steps):
                step = WorkflowStep(
                    workflow_id=workflow.id,
                    step_type=step_data["step_type"],
                    definition=step_data.get("definition", {}),
                    position=i,
                    condition_expr=step_data.get("condition_expr", ""),
                    is_enabled=step_data.get("is_enabled", True),
                    title=step_data.get("title", ""),
                    description=step_data.get("description", ""),
                    tenant_id=workflow.tenant_id
                )
                db.add(step)

        # H7 fix: auto-increment version only when manual_version_increment was NOT set.
        # Previously both the manual block (line ~256) and this unconditional increment
        # fired together, producing a +2 bump on a single save.
        if not workflow_data.manual_version_increment:
            workflow.version += 1
        # §2.4: capture this version's snapshot. The snapshot query's autoflush flushes
        # the deleted/recreated steps so the stored definition reflects the new graph.
        await snapshot_workflow(
            db, workflow, workflow.version,
            label=workflow_data.version_label or "", created_by=created_by,
        )
        await db.commit()
        await db.refresh(workflow)
        return workflow

    async def delete_workflow(self, db: AsyncSession, workflow_id: int) -> bool:
        """Deactivate a workflow (soft-delete), preserving runs for audit"""
        stmt = select(Workflow).where(Workflow.id == workflow_id)
        result = await db.execute(stmt)
        workflow = result.scalar_one_or_none()

        if not workflow:
            return False

        workflow.is_active = False
        await db.commit()
        return True
    
    async def trigger_workflow(self, db: AsyncSession, workflow_id: int, run_data: WorkflowRunCreate) -> WorkflowRun:
        """Trigger a new workflow run"""
        # Get workflow with steps and service
        stmt = (
            select(Workflow)
            .where(Workflow.id == workflow_id)
            .options(selectinload(Workflow.steps), selectinload(Workflow.service))
        )
        result = await db.execute(stmt)
        workflow = result.scalar_one()

        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        if not workflow.is_active:
            raise ValueError(f"Workflow {workflow_id} is not active")

        # Populate SLA targets from service config (Phase 5)
        sla_response_target = None
        sla_resolution_target = None
        if workflow.service:
            sla_config = (workflow.service.custom_data or {}).get("sla_targets", {})
            priority_key = str(run_data.priority) if run_data.priority else None
            # Check priority override first, then fall back to default
            if priority_key and priority_key in sla_config.get("response_hours", {}):
                sla_response_target = sla_config["response_hours"][priority_key]
            elif sla_config.get("response_hours", {}).get("default") is not None:
                sla_response_target = sla_config["response_hours"]["default"]
            if priority_key and priority_key in sla_config.get("resolution_hours", {}):
                sla_resolution_target = sla_config["resolution_hours"][priority_key]
            elif sla_config.get("resolution_hours", {}).get("default") is not None:
                sla_resolution_target = sla_config["resolution_hours"]["default"]

        # Create run
        run = WorkflowRun(
            workflow_id=workflow_id,
            status="pending",
            triggered_by=run_data.triggered_by,
            workflow_name=workflow.name or "",
            input_data=run_data.input_data,
            timeout_seconds=run_data.timeout_seconds,
            max_retries=run_data.max_retries,
            failure_hooks=run_data.failure_hooks,
            priority=run_data.priority,
            service_id=run_data.service_id or workflow.service_id,
            sla_response_target_hours=sla_response_target,
            sla_resolution_target_hours=sla_resolution_target,
            tenant_id=workflow.tenant_id,
        )
        db.add(run)
        await db.flush()

        # Create step instances
        for step in workflow.steps:
            instance = StepInstance(
                workflow_run_id=run.id,
                step_id=step.id,
                step_title=step.title or step.step_type or "",
                step_type=step.step_type,
                step_description=step.description or "",
                step_definition=dict(step.definition or {}),
                status="pending",
                input_data=run_data.input_data.copy(),
                position=step.position,
                max_retries=step.max_retries or run_data.max_retries,
                tenant_id=workflow.tenant_id,
            )
            db.add(instance)
        
        await db.commit()
        await db.refresh(run)
        
        # Execute workflow asynchronously with its own session
        asyncio.create_task(self._execute_workflow(run.id))
        
        return run
    
    async def _check_timeout(self, db, run):
        """Check if the run has exceeded its timeout. Returns True if timed out."""
        if run.timeout_seconds <= 0:
            return False

        started = run.started_at
        # ``started_at`` is a timestamptz column. On the first run it is set in
        # memory as a naive datetime; on a resumed run it is re-loaded from the
        # DB as tz-aware. Normalize to aware so the subtraction below can't raise
        # ``TypeError: can't compare offset-naive and offset-aware datetimes``.
        if started is not None and started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        if elapsed > run.timeout_seconds:
            run.status = "timeout"
            run.error_message = f"Run timed out after {run.timeout_seconds} seconds (elapsed: {elapsed:.1f}s)"
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()
            
            notify_admin(
                f"Workflow run timed out: {run.id}",
                f"Run {run.id} exceeded timeout of {run.timeout_seconds} seconds.\n"
                f"Elapsed time: {elapsed:.1f} seconds\n"
                f"Status: {run.status}"
            )
            return True
        return False
    
    async def _execute_workflow(self, run_id: int):
        """Execute a workflow run using its own database session"""
        async with async_session_factory() as db:
            try:
                # Get run (don't load instances — they'll be loaded fresh in branch sessions)
                stmt = select(WorkflowRun).where(WorkflowRun.id == run_id)
                result = await db.execute(stmt)
                run = result.scalar_one()

                # Update status to running
                run.status = "running"
                # M3 fix: only set started_at on the initial trigger, not on resume.
                # Previously every resume_workflow call overwrote started_at to now(),
                # resetting the timeout clock and allowing infinite evasion.
                if run.started_at is None:
                    run.started_at = datetime.utcnow()
                await db.commit()
                
                # Load all workflow steps
                wf_stmt = select(Workflow).where(Workflow.id == run.workflow_id).options(selectinload(Workflow.steps))
                wf_result = await db.execute(wf_stmt)
                workflow = wf_result.scalar_one()
                step_lookup = {s.id: s for s in workflow.steps}
                
                # Load instances fresh from DB (not from identity map)
                instances_stmt = select(StepInstance).where(StepInstance.workflow_run_id == run_id)
                instances_result = await db.execute(instances_stmt)
                step_instances = sorted(instances_result.scalars().all(), key=lambda x: x.position)
                instance_lookup = {inst.step_id: inst for inst in step_instances}
                
                # Check if the workflow uses an explicit graph (connections / start config)
                config = workflow.config or {}
                has_explicit_start = bool(config.get("start_step_ids"))
                has_connections = any(
                    s.definition.get("next_step_id") or 
                    s.definition.get("next_step_ids") or
                    any(r.get("target_step_id") for r in s.definition.get("routes", []) if r.get("target_step_id"))
                    for s in workflow.steps
                )
                has_branches = has_explicit_start or has_connections
                
                if not has_branches:
                    # Legacy: simple linear execution with condition skip.
                    # Resume-aware: steps already in a terminal status are not
                    # re-executed; a human step whose task is still open re-pauses.
                    for instance in step_instances:
                        # Check timeout before each step
                        if await self._check_timeout(db, run):
                            break
                        
                        if run.status != "running":
                            break
                        step = step_lookup.get(instance.step_id)
                        if not step:
                            continue
                        if instance.status in ("completed", "failed", "skipped"):
                            if step.step_type in ("human_task", "approval") and not await self._human_task_resolved(db, run_id, step.id):
                                run.status = "waiting"
                                await db.commit()
                                break
                            continue
                        if step.condition_expr and not self._evaluate_condition(step.condition_expr, instance.input_data):
                            instance.status = "skipped"
                            instance.completed_at = datetime.utcnow()
                            self._record_route(instance, self._linear_next(step_instances, instance))
                            await db.commit()
                            continue
                        success = await self._execute_single_step(db, run, instance, step)
                        if success:
                            self._record_route(instance, self._linear_next(step_instances, instance))
                            await db.commit()
                        else:
                            break
                else:
                    # Graph mode: follow explicit connections. Branches are executed
                    # sequentially via _execute_branching_sync; the visited set still
                    # ensures each step runs at most once per run (DAG semantics).
                    await self._execute_branching_sync(db, run, run_id, workflow, step_instances)
                
                if run.status == "running":
                    run.status = "completed"

                # I3/I13 fix: include "timeout" and "cancelled" in the terminal set
                # so that completed_at is stamped for all non-running final states.
                if run.status in ("completed", "failed", "timeout", "cancelled"):
                    run.completed_at = datetime.utcnow()
                    # SLA resolution tracking (Phase 5)
                    if run.sla_resolution_target_hours is not None and run.sla_resolution_met is None and run.started_at:
                        from datetime import timezone as tz
                        start = run.started_at.replace(tzinfo=tz.utc) if run.started_at.tzinfo is None else run.started_at
                        elapsed_hours = (datetime.now(tz.utc) - start).total_seconds() / 3600
                        run.sla_resolution_met = elapsed_hours <= run.sla_resolution_target_hours

                run.output_data = run.input_data.copy()
                
                # Only commit the run, not the instances (they were committed by branch sessions)
                await db.commit()
                
            except Exception as e:
                logger.error(f"Workflow run {run_id} failed: {str(e)}")
                try:
                    run_stmt = select(WorkflowRun).where(WorkflowRun.id == run_id)
                    run_result = await db.execute(run_stmt)
                    run = run_result.scalar_one()
                    run.status = "failed"
                    run.error_message = f"Run {run_id}: {str(e)}"
                    run.completed_at = datetime.utcnow()
                    await db.commit()
                except:
                    pass
                notify_admin(f"Workflow run {run_id} failed", str(e))
                # G4: also push the failure through configured external channels
                # (email / Slack / signed webhook). Best-effort; never raises.
                try:
                    from app.services.notification_service import notify_admins

                    await notify_admins(
                        type="workflow_failed",
                        title=f"Workflow run {run_id} failed",
                        message=str(e),
                        context={"run_id": run_id},
                    )
                except Exception:
                    logger.exception("Failed to dispatch workflow_failed notification channel")
    
    async def _execute_single_step(self, db, run, instance, step) -> bool:
        """Execute a single step with retry support. Returns True if execution should continue."""
        max_retries = step.max_retries or run.max_retries
        
        for attempt in range(max_retries + 1):
            try:
                instance.status = "running"
                instance.started_at = datetime.utcnow()
                instance.retry_count = attempt
                await db.commit()
                
                # Handle human_task and approval steps specially
                if step.step_type in ["human_task", "approval"]:
                    return await self._handle_human_step(db, run, instance, step)
                
                executor = self.step_executors.get(step.step_type)
                if not executor:
                    raise ValueError(f"No executor for step type: {step.step_type}")

                # Inject run ID so executors (e.g. CalculationExecutor date_target) can reference it
                step_input = dict(instance.input_data or {})
                step_input.setdefault("_workflow_run_id", run.id)
                step_input.setdefault("_workflow_step_id", step.id)

                # G2: resolve cross-step / scoped references ({{ step.<id>.output.<f> }},
                # {{ input.<f> }}) in the definition against accumulated input + prior
                # step outputs. Only queries when the definition actually contains a
                # template, so the common case has zero extra cost.
                step_definition = step.definition
                if context_has_templates(step.definition):
                    ref_ctx = await self._reference_context(db, run, instance.id)
                    step_definition = interpolate(step.definition, ref_ctx)

                output_data = await executor.execute(step_input, step_definition, db=db)
                
                instance.status = "completed"
                instance.output_data = output_data
                instance.completed_at = datetime.utcnow()
                instance.retry_count = 0  # Reset retry count on success
                instance.last_error = ""
                
                # Update run input for next steps
                run.input_data = {**(run.input_data or {}), **output_data}
                
                await db.commit()
                return True
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Step {instance.id} attempt {attempt + 1} failed: {error_msg}")
                
                # Store last error for retry
                instance.last_error = error_msg
                
                if attempt < max_retries:
                    # Wait before retry (if configured)
                    retry_delay = step.retry_delay_seconds or 0
                    if retry_delay > 0:
                        logger.info(f"Retrying step {instance.id} in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                    continue
                else:
                    # All retries exhausted, mark as failed
                    instance.status = "failed"
                    instance.error_message = f"Step failed after {max_retries + 1} attempts: {error_msg}"
                    instance.completed_at = datetime.utcnow()
                    
                    run.status = "failed"
                    run.error_message = f"Run {run.id}: Step {instance.id} failed after {max_retries + 1} attempts: {error_msg}"
                    
                    # Execute failure hooks
                    await self._execute_failure_hooks(db, run, instance, step, error_msg)
                    
                    # Send admin notice
                    notify_admin(
                        f"Step failed in workflow run {run.id}",
                        f"Step {instance.id} ({step.title or step.step_type}) failed after {max_retries + 1} attempts.\n"
                        f"Error: {error_msg}\n"
                        f"Run ID: {run.id}"
                    )
                    
                    await db.commit()
                    return False
        
        # Should not reach here, but just in case
        instance.status = "failed"
        instance.error_message = "Unknown error"
        instance.completed_at = datetime.utcnow()
        run.status = "failed"
        run.error_message = f"Run {run.id}: Step {instance.id} failed"
        await db.commit()
        return False

    async def _reference_context(self, db, run, exclude_instance_id: Optional[int] = None):
        """Build a G2 :class:`ReferenceContext` for cross-step / scoped references.

        ``input_data`` is the accumulated run input (the flat, merged blob of every
        prior step's outputs). ``step_outputs`` maps each *workflow step id* to that
        step's ``output_data`` so a step can reference an earlier one by identity
        (``step.<id>.output.<field>``) instead of relying on merge order.

        Prior outputs are read from committed completed/skipped StepInstances of this
        run. Under true fan-in every predecessor is committed before a converging step
        runs, so querying committed rows is race-free across the separate per-branch
        sessions used by the concurrent scheduler. Any query failure degrades to an
        empty ``step_outputs`` map (input references still work) rather than failing
        the run.
        """
        input_data = dict(run.input_data or {})
        step_outputs: Dict[int, Dict[str, Any]] = {}
        try:
            stmt = select(StepInstance).where(
                StepInstance.workflow_run_id == run.id,
                StepInstance.status.in_(("completed", "skipped")),
            )
            if exclude_instance_id is not None:
                stmt = stmt.where(StepInstance.id != exclude_instance_id)
            result = await db.execute(stmt)
            for inst in result.scalars().all():
                if inst.output_data and isinstance(inst.output_data, dict):
                    step_outputs[int(inst.step_id)] = inst.output_data
        except Exception as e:  # pragma: no cover - defensive; never fail a run on refs
            logger.debug(f"G2 reference context build failed for run {run.id}: {e}")
        return ReferenceContext(input_data=input_data, step_outputs=step_outputs)

    async def _execute_failure_hooks(self, db, run, instance, step, error_msg):
        """Execute failure hooks configured for the workflow or step."""
        import httpx
        
        # Get failure hooks from run config (workflow-level)
        hooks = run.failure_hooks or []
        
        # Also check step-level failure hook
        if step.failure_hook_url:
            hooks.append({"url": step.failure_hook_url, "type": "step"})
        
        if not hooks:
            return
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            for hook in hooks:
                try:
                    url = hook.get("url")
                    if not url:
                        continue
                    
                    payload = {
                        "run_id": run.id,
                        "step_id": instance.step_id,
                        "step_type": step.step_type,
                        "status": "failed",
                        "error": error_msg,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    
                    response = await client.post(url, json=payload)
                    logger.info(f"Failure hook {url} responded with status {response.status_code}")
                    
                except Exception as e:
                    logger.error(f"Failed to execute failure hook {hook.get('url')}: {str(e)}")
    
    async def _prefill_from_run_data(self, db, form_id: int, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Return the subset of run input data matching the form's field names,
        so a human task form is pre-filled with values entered earlier in the run
        (e.g. the user's entry-form submission)."""
        from app.models.forms import Form
        result = await db.execute(select(Form).where(Form.id == form_id))
        form = result.scalar_one_or_none()
        if not form or not form.schema_json:
            return {}
        schema = form.schema_json if isinstance(form.schema_json, dict) else {}
        properties = schema.get("properties") or {}
        return {key: value for key, value in (input_data or {}).items() if key in properties}

    async def _handle_human_step(self, db, run, instance, step) -> bool:
        """Handle human_task or approval steps - create task and pause workflow"""
        definition = step.definition or {}
        
        # Extract assignment info
        assigned_to_user_id = definition.get("assigned_to_user_id")
        assigned_group_id = definition.get("assigned_group_id")
        form_id = definition.get("form_id")
        
        # Prefill the task form with data accumulated earlier in the run
        # (e.g. an entry-form submission). Explicit per-step task_data wins.
        task_data = dict(definition.get("task_data", {}) or {})
        if form_id:
            prefill = await self._prefill_from_run_data(db, form_id, run.input_data)
            for key, value in prefill.items():
                task_data.setdefault(key, value)
        
        # OLA: populate targets from assigned group's config + run priority
        ola_pickup_target = None
        ola_closure_target = None
        if assigned_group_id:
            from app.models.auth import Group
            grp_stmt = select(Group).where(Group.id == assigned_group_id)
            grp_result = await db.execute(grp_stmt)
            group = grp_result.scalar_one_or_none()
            if group:
                ola_config = (group.custom_data or {}).get("ola_targets", {})
                priority_key = str(run.priority) if run.priority else None
                # Check priority override first, then fall back to default
                if priority_key and priority_key in ola_config.get("pickup_hours", {}):
                    ola_pickup_target = ola_config["pickup_hours"][priority_key]
                elif ola_config.get("pickup_hours", {}).get("default") is not None:
                    ola_pickup_target = ola_config["pickup_hours"]["default"]
                if priority_key and priority_key in ola_config.get("closure_hours", {}):
                    ola_closure_target = ola_config["closure_hours"][priority_key]
                elif ola_config.get("closure_hours", {}).get("default") is not None:
                    ola_closure_target = ola_config["closure_hours"]["default"]

        # Create task
        task = Task(
            workflow_run_id=run.id,
            step_id=step.id,
            title=f"Task: {step.title if hasattr(step, 'title') else step.step_type}",
            description=definition.get("description", ""),
            status="open",
            assigned_to_user_id=assigned_to_user_id,
            assigned_group_id=assigned_group_id,
            form_id=form_id,
            task_data=task_data,
            result_data={},
            priority=run.priority,
            ola_pickup_target_hours=ola_pickup_target,
            ola_closure_target_hours=ola_closure_target,
            tenant_id=run.tenant_id,
        )

        db.add(task)
        await db.flush()
        
        # Mark step instance as completed (but workflow pauses here)
        instance.status = "completed"
        instance.output_data = {"task_id": task.id, "status": "pending_human_action"}
        instance.completed_at = datetime.utcnow()
        
        run.input_data = {**(run.input_data or {}), **instance.output_data}
        # Mark workflow as waiting on human action (resume continues from here)
        run.status = "waiting"

        # Notify the assignee that they have a new task (Feature-Plan §2.3). Flushed
        # here so it commits alongside the task above and rolls back with it.
        if assigned_to_user_id:
            from app.models.auth import User
            from app.services.notification_service import notify

            # Fetch the assignee so the notification can also be pushed through
            # configured external channels (G4) -- e.g. email to the assignee.
            user = (
                await db.execute(select(User).where(User.id == assigned_to_user_id))
            ).scalar_one_or_none()

            await notify(
                db,
                user,
                type="task_assigned",
                title=f"Task assigned: {task.title}",
                message="You have been assigned a task in a running workflow.",
                related_entity_type="task",
                related_entity_id=task.id,
            )

        await db.commit()
        
        logger.info(f"Created task {task.id} for step {step.id}, workflow paused at human step")
        
        # Return False to pause workflow execution
        return False
    
    async def resume_workflow(self, run_id: int):
        """Resume a paused workflow after task completion (P3.2)."""
        async with async_session_factory() as db:
            stmt = select(WorkflowRun).where(WorkflowRun.id == run_id)
            result = await db.execute(stmt)
            run = result.scalar_one_or_none()
            
            if not run or run.status != "waiting":
                logger.warning(f"Cannot resume workflow run {run_id}: not in waiting state (status={run.status if run else 'None'})")
                return
            
            # Find the workflow
            workflow_stmt = select(Workflow).where(Workflow.id == run.workflow_id)
            workflow_result = await db.execute(workflow_stmt)
            workflow = workflow_result.scalar_one_or_none()
            
            if not workflow:
                logger.error(f"Workflow {run.workflow_id} not found for run {run_id}")
                return
            
            # Get all step instances for this run
            instances_stmt = select(StepInstance).where(StepInstance.workflow_run_id == run_id)
            instances_result = await db.execute(instances_stmt)
            step_instances = instances_result.scalars().all()
            
            # Find the human_task/approval step that's waiting and update its output with task result
            for instance in step_instances:
                if instance.status == "completed" and instance.output_data.get("status") == "pending_human_action":
                    # Find associated task
                    task_stmt = select(Task).where(
                        Task.workflow_run_id == run_id,
                        Task.step_id == instance.step_id,
                        Task.status == "completed"
                    )
                    task_result = await db.execute(task_stmt)
                    task = task_result.scalar_one_or_none()
                    
                    if task:
                        # Update step instance output with task result
                        instance.output_data = {
                            **instance.output_data,
                            "task_result": task.result_data,
                            "status": "task_completed",
                        }
                        instance.completed_at = datetime.utcnow()
                        # Feed the task result back into the run so later
                        # human-task forms can be pre-filled with it too
                        run.input_data = {**(run.input_data or {}), **(task.result_data or {})}
                        logger.info(f"Updated step instance {instance.id} output with task result")
            
            await db.commit()
            
            logger.info(f"Resuming workflow run {run_id} with {len(step_instances)} step instances")
            
            # Mark run as running and re-execute the workflow (this will pick up where it left off)
            run.status = "running"
            await db.commit()
            await self._execute_workflow(run_id)
    
    async def _execute_branching(self, db, run, run_id: int, workflow: Workflow, step_instances):
        """Execute a workflow following explicit connections.

        Deprecated in favour of :meth:`_execute_branching_sync`; retained for
        backward compatibility and now delegates to the synchronous implementation.
        Branches are executed sequentially (not concurrently) to avoid per-path DB
        session management issues; the ``visited`` set guarantees each step runs at
        most once per run.
        """
        await self._execute_branching_sync(db, run, run_id, workflow, step_instances)

    async def _execute_branching_sync(self, db, run, run_id: int, workflow: Workflow, step_instances):
        """Execute a workflow following explicit connections with TRUE PARALLEL execution
        and true fan-in synchronization (G1).

        Independent branches run concurrently via asyncio; a converging step waits for
        ALL of its predecessors to complete before running (fan-in) and runs at most
        once per run (DAG semantics). This replaces the old sequential depth-first
        traversal, which ran branches one after another and — because it shared a
        ``visited`` set — executed a converging step on the *first* path that reached
        it, silently dropping every other branch.

        Model (event-driven DAG scheduler, all state below is shared via closure):

        * Each node has a predecessor counter initialized to its static predecessor
          count. A predecessor "releases" a successor (decrements its counter) when it
          resolves — whether it executed, was skipped/disabled, or was an orphaned
          branch that never ran.
        * A node becomes runnable when its counter hits zero AND it was actually reached
          by at least one predecessor (or is a wired start node).
        * Orphaned nodes (all predecessors resolved but none routed to them) still
          release their own successors, so counters can never deadlock.
        * Resume-aware: instances already in a terminal state (from a prior partial run)
          are "pre-resolved" — their successors are released up front — so the live
          scheduler only drives the not-yet-run portion of the graph.
        """
        instance_lookup = {inst.step_id: inst for inst in step_instances}
        step_lookup = {s.id: s for s in workflow.steps}

        # In-memory coordination state shared across all concurrent branch tasks. Each
        # task runs on its own AsyncSession (see note in _RunCtx); this object is the
        # single source of truth for accumulated input (fan-in) and run status.
        ctx = _RunCtx(run)
        # step_id -> StepInstance.db id, so each task can load its own instance copy.
        step_to_inst_id = {sid: inst.id for sid, inst in instance_lookup.items()}

        config = workflow.config or {}
        start_ids = set(i for i in config.get("start_step_ids", []) if i in instance_lookup)

        # Static successor map (a SUPERSET of the actually-taken targets). Using a
        # superset guarantees every real predecessor releases each successor exactly
        # once -> no deadlock even when condition branches drop some edges.
        static_succ = {sid: self._static_targets(step_lookup[sid]) for sid in instance_lookup}

        # Static reachability from the wired start nodes, so a dangling predecessor that
        # points at a reachable node (but is itself unreachable) is not counted — it
        # would never resolve and would deadlock the counter.
        reachable = self._static_reachable(start_ids, static_succ)

        preds = {
            tid: [pid for pid in static_succ
                  if tid in static_succ.get(pid, ()) and pid in reachable]
            for tid in instance_lookup
        }

        counter = {tid: len(preds[tid]) for tid in instance_lookup}
        reached = {tid: set() for tid in instance_lookup}
        executed = {tid: False for tid in instance_lookup}
        created = {tid: False for tid in instance_lookup}
        resolved: set[int] = set()
        tasks: dict = {}

        async def spawn(tid):
            if created.get(tid) or tid not in reachable or tid in resolved:
                return
            created[tid] = True
            # ``dag_step`` is the nested closure defined below (it closes over db/run/
            # run_id and all the shared state dicts); it is NOT a method on self.
            tasks[tid] = asyncio.create_task(dag_step(tid))

        async def handle_ready(succ):
            """Called when ``succ``'s predecessor counter has just hit zero."""
            if succ in resolved or executed[succ] or counter[succ] != 0:
                return
            # Runnable only if it was actually reached, or it is a wired start node.
            if succ in start_ids or reached[succ]:
                await spawn(succ)
            else:
                # Orphaned branch (all predecessors resolved but none routed here). It
                # must still release its own successors so their counters can reach zero.
                for s2 in static_succ.get(succ, ()):
                    if s2 not in counter:
                        continue
                    counter[s2] -= 1
                    if counter[s2] == 0:
                        await handle_ready(s2)

        async def release(tid, route):
            """Decrement each static successor's predecessor counter, mark successors that
            were actually routed to as ``reached``, and spawn/handle any that become
            runnable (counter hit zero). Shared by live execution, disabled-step skip, and
            resume-aware pre-resolution so fan-in counting stays consistent everywhere."""
            for succ in static_succ.get(tid, ()):
                if succ not in counter:
                    continue
                if succ in route:
                    reached[succ].add(tid)
                counter[succ] -= 1
                if counter[succ] == 0:
                    await handle_ready(succ)

        async def dag_step(step_id):
            """Execute a single node of the DAG (one asyncio task). Runs concurrently
            with sibling nodes on its OWN database session, so concurrent commits can't
            corrupt a shared session's transaction state. Fan-in synchronization is
            provided by the caller via the predecessor counter before this task spawns."""
            instance_id = step_to_inst_id.get(step_id)
            if instance_id is None:
                return

            async with async_session_factory() as tdb:
                # Load a fresh copy of this instance for this branch's session.
                instance = await tdb.get(StepInstance, instance_id)
                step = step_lookup.get(step_id)  # read-only; definition never changes
                if instance is None or step is None:
                    return
                executed[step_id] = True

                # Timeout guard (checked per step, like the sequential model).
                if await self._check_timeout(tdb, ctx):
                    return

                # Resume-aware: a step already in a terminal state is resolved without
                # re-running; replay its routes so successors can be released.
                if instance.status in ("completed", "skipped"):
                    if step.step_type in ("human_task", "approval") and not await self._human_task_resolved(tdb, run_id, step.id):
                        ctx.status = "waiting"
                        await tdb.commit()
                        return
                    # Re-evaluate the route exactly as a fresh execution would (raises on
                    # a bad/empty condition route, which fails the run).
                    route = self._get_targets(step, ctx.input_data)
                    await release(step_id, route)
                    return

                # Skip disabled steps — mark skipped but still propagate along routes.
                if not step.is_enabled:
                    instance.status = "skipped"
                    instance.output_data = {"skipped_reason": "step_disabled"}
                    instance.completed_at = datetime.utcnow()
                    await tdb.commit()
                    route = self._get_targets(step, ctx.input_data)
                    for t in route:
                        self._record_route_instance(instance, t)
                    await release(step_id, route)
                    return

                # Merge accumulated run data into this step's input (fan-in: a converging
                # step sees every predecessor's outputs, since each merged into
                # ctx.input_data before releasing it).
                instance.input_data = {**(instance.input_data or {}), **ctx.input_data, "_workflow_run_id": ctx.id}

                success = await self._execute_single_step(tdb, ctx, instance, step)
                if not success:
                    # Failure (or human pause) already set ctx.status. Do not propagate
                    # from this branch; siblings finish on their own and the run ends terminal.
                    return

                # Record the route taken for the run inspector, then release successors.
                # _get_targets raises ValueError on a bad/empty condition route, which
                # fails the run — matching the sequential model's behavior.
                route = self._get_targets(step, ctx.input_data)
                self._record_route(instance, route)
                await tdb.commit()
                await release(step_id, route)

        # --- Resume-aware pre-resolution: replay already-terminal instances so the live
        #     scheduler only has to drive the not-yet-run portion of the graph. Replay a
        #     completed instance's output back into ctx.input_data so a converging step
        #     still sees every predecessor's outputs after a resume (fan-in). ---
        for inst in step_instances:
            if inst.status not in ("completed", "skipped"):
                continue
            resolved.add(inst.step_id)
            step = step_lookup.get(inst.step_id)
            if step is None:
                continue
            if inst.output_data:
                ctx.input_data = {**ctx.input_data, **(inst.output_data or {})}
            route = self._get_targets(step, ctx.input_data)
            await release(inst.step_id, route)

        # --- Kick off the wired start nodes. ---
        for sid in start_ids:
            await handle_ready(sid)

        # --- Await everything, including tasks spawned while others run. ---
        while True:
            pending = [t for t in tasks.values() if not t.done()]
            if not pending:
                break
            results = await asyncio.gather(*pending, return_exceptions=True)
            # A step failure/route error is recorded on ``ctx`` (or raised) inside
            # dag_step; surface any unexpected exception so it isn't silently swallowed.
            for r in results:
                if isinstance(r, Exception) and not isinstance(r, asyncio.CancelledError):
                    raise r

        # --- Sync the in-memory coordination state back onto the ORM run so the caller's
        #     finalize (status -> completed, completed_at, error, SLA, output_data) sees it.
        #     These were written on the shared _RunCtx by the branch tasks (each task has
        #     its own session), so they must be copied back before the caller commits. ---
        run.status = ctx.status
        run.input_data = ctx.input_data
        run.error_message = ctx.error_message

        # --- Mark anything never reached as skipped (matches prior behavior). ---
        # ``executed`` is a dict keyed by step id with a False value for steps that never
        # ran, so the check must read the *value* (``not executed[...]``), not test key
        # presence (every id is always a key).
        finalized = False
        for inst in step_instances:
            if inst.status == "pending" and not executed.get(inst.step_id, False) and inst.step_id not in resolved:
                inst.status = "skipped"
                inst.completed_at = datetime.utcnow()
                finalized = True
        if finalized:
            await db.commit()

    def _record_route_instance(self, instance, target):
        """Record a single route_taken target on an instance's custom_data."""
        custom = dict(instance.custom_data or {})
        taken = list(custom.get("route_taken") or [])
        if int(target) not in taken:
            taken.append(int(target))
        custom["route_taken"] = taken
        instance.custom_data = custom

    def _static_targets(self, step) -> tuple:
        """Return the static (potential) successor step ids of ``step`` — a superset of
        what :meth:`_get_targets` can return at runtime. Over-approximating is safe: it
        only makes a node wait for predecessors that will resolve anyway."""
        d = step.definition or {}
        ids: set = set()
        if step.step_type in ("condition", "ai_condition"):
            for r in d.get("routes") or []:
                t = r.get("target_step_id")
                if t is not None:
                    ids.add(t)
            for key in ("on_true", "on_false"):
                if d.get(key) is not None:
                    ids.add(d[key])
        ids.update(d.get("next_step_ids") or [])
        if d.get("next_step_id") is not None:
            ids.add(d["next_step_id"])
        return tuple(i for i in ids if i is not None)

    @staticmethod
    def _static_reachable(start_ids, static_succ) -> set:
        """Set of step ids reachable from ``start_ids`` over the static successor map."""
        seen: set = set()
        stack = list(start_ids)
        while stack:
            sid = stack.pop()
            if sid in seen:
                continue
            seen.add(sid)
            for nxt in static_succ.get(sid, ()):
                if nxt not in seen:
                    stack.append(nxt)
        return seen

    def _get_targets(self, step: WorkflowStep, input_data: Dict[str, Any]) -> List[int]:
        """Return the target step ids a step connects to based on its definition."""
        d = step.definition or {}
        if step.step_type == "condition":
            routes, default = self._normalize_condition(step)
            for route in routes:
                expr = route.get("expression") or ""
                target = route.get("target_step_id")
                if not expr:
                    raise ValueError(
                        "Condition step has an empty expression in a route "
                        f"(target_step_id={target}). Use default_target_step_id for "
                        "an unconditional route."
                    )
                if target is not None and self._evaluate_condition(expr, input_data):
                    return [target]
            if default is not None:
                return [default]
            return []
        ids = d.get("next_step_ids") or []
        if not ids and d.get("next_step_id"):
            ids = [d["next_step_id"]]
        return [i for i in ids]

    def _record_route(self, instance: StepInstance, targets) -> None:
        """Record which target step ids an instance routed to (run inspector)."""
        if instance is None:
            return
        custom = dict(instance.custom_data or {})
        custom["route_taken"] = [int(t) for t in targets]
        instance.custom_data = custom

    def _linear_next(self, instances, current) -> List[int]:
        """Target step id of the next instance in linear (position) order."""
        ordered = sorted(
            (i.position or 0, i) for i in instances
        )
        current_pos = current.position or 0
        for pos, inst in ordered:
            if pos > current_pos and inst.step_id is not None:
                return [inst.step_id]
        return []

    def _normalize_condition(self, step: WorkflowStep) -> tuple:
        """Return (routes, default) for a condition step.

        Model B (designer): routes[] each {expression, target_step_id} plus an
        optional default_target_step_id. Legacy shapes are backfilled:
        step-level condition_expr + definition.on_true/on_false, and Model A
        definition.expression (ai_service). Backfilled routes are re-evaluated
        every run, so a legacy on_true/on_false without an expression becomes an
        empty-expression error rather than a silent always-true branch.
        """
        d = step.definition or {}
        routes = [dict(r) for r in d.get("routes") or []]
        default = d.get("default_target_step_id")
        if routes:
            return routes, default
        expr = (step.condition_expr or "").strip() or d.get("expression")
        on_true = d.get("on_true")
        on_false = d.get("on_false")
        if on_true is not None or on_false is not None:
            routes = [{"expression": expr or "", "target_step_id": on_true}]
            if on_false is not None and default is None:
                default = on_false
        elif expr:
            routes = [{"expression": expr, "target_step_id": None}]
        return routes, default

    def _evaluate_condition(self, condition_expr: str, data: Dict[str, Any]) -> bool:
        """Evaluate a condition expression using safe AST-based evaluation.

        Allowed operations: comparisons, boolean ops, arithmetic, subscript access
        on ``data``, and attribute access on leaf values (not on dict proxies).
        """
        try:
            tree = ast.parse(condition_expr, mode="eval")
            return bool(self._safe_eval(node=tree.body, data=data))
        except Exception as e:
            raise ValueError(
                f"Condition evaluation failed for expression {condition_expr!r}: "
                f"{type(e).__name__}: {e}"
            ) from e

    def _safe_eval(self, node: ast.AST, data: Dict[str, Any]) -> Any:
        """Recursively evaluate an AST node with restricted operations."""
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id == "data":
                return data
            raise ValueError(f"Name {node.id!r} not in scope (expected 'data')")
        if isinstance(node, ast.Subscript):
            value = self._safe_eval(node.value, data)
            if isinstance(node.slice, ast.Constant):
                return value[node.slice.value]
            if isinstance(node.slice, ast.Index):
                return value[self._safe_eval(node.slice.value, data)]
            raise ValueError(f"Subscript slice type {type(node.slice).__name__}")
        if isinstance(node, ast.Attribute):
            obj = self._safe_eval(node.value, data)
            # Gate dunder access (e.g. __class__.__mro__[1].__subclasses__() /
            # __globals__) so that fixing the Call handler (#8a) cannot turn condition
            # steps into an RCE. Legitimate calls (.upper(), .split(), .get()) are not
            # dunders and keep working. Mirrors _RestrictedProxy in step_executors.py.
            if node.attr.startswith("__"):
                raise ValueError(
                    f"Attribute {node.attr!r} is not allowed in conditions"
                )
            return getattr(obj, node.attr)
        if isinstance(node, ast.Compare):
            left = self._safe_eval(node.left, data)
            results = []
            for op, comparator in zip(node.ops, node.comparators):
                right = self._safe_eval(comparator, data)
                results.append(self._compare(left, op, right))
                left = right
            return all(results)
        if isinstance(node, ast.BoolOp):
            values = [self._safe_eval(v, data) for v in node.values]
            if isinstance(node.op, ast.And):
                return all(values)
            return any(values)
        if isinstance(node, ast.UnaryOp):
            operand = self._safe_eval(node.operand, data)
            if isinstance(node.op, ast.Not):
                return not operand
            if isinstance(node.op, ast.USub):
                return -operand
            raise ValueError(f"UnaryOp {type(node.op).__name__}")
        if isinstance(node, ast.BinOp):
            left = self._safe_eval(node.left, data)
            right = self._safe_eval(node.right, data)
            op_map = {
                ast.Add: lambda a, b: a + b,
                ast.Sub: lambda a, b: a - b,
                ast.Mult: lambda a, b: a * b,
                ast.Div: lambda a, b: a / b,
                ast.Mod: lambda a, b: a % b,
                ast.Pow: lambda a, b: a ** b,
                ast.Eq: lambda a, b: a == b,
                ast.NotEq: lambda a, b: a != b,
            }
            fn = op_map.get(type(node.op))
            if fn:
                return fn(left, right)
            raise ValueError(f"BinOp {type(node.op).__name__}")
        if isinstance(node, ast.Call):
            func = self._safe_eval(node.func, data)
            args = [self._safe_eval(a, data) for a in node.args]
            # node.keywords is a list of ast.keyword nodes; each exposes .arg and
            # .value. The previous `zip(node.keywords, node.values)` was wrong: an
            # ast.Call has no .values attribute, so *every* function/method call in a
            # condition raised AttributeError (findings #8a). Iterate keywords directly
            # and read the value node from each keyword (mirrors app/services/safe_eval.py).
            kwargs = {
                k.arg: self._safe_eval(k.value, data)
                for k in node.keywords
                if k.arg is not None
            }
            return func(*args, **kwargs)
        raise ValueError(f"AST node type {type(node).__name__} not supported")

    @staticmethod
    def _compare(left: Any, op: ast.cmpop, right: Any) -> bool:
        """Evaluate a single comparison operator."""
        op_map = {
            ast.Eq: lambda a, b: a == b,
            ast.NotEq: lambda a, b: a != b,
            ast.Lt: lambda a, b: a < b,
            ast.LtE: lambda a, b: a <= b,
            ast.Gt: lambda a, b: a > b,
            ast.GtE: lambda a, b: a >= b,
            ast.Is: lambda a, b: a is b,
            ast.IsNot: lambda a, b: a is not b,
            ast.In: lambda a, b: a in b,
            ast.NotIn: lambda a, b: a not in b,
        }
        fn = op_map.get(type(op))
        if fn:
            return fn(left, right)
        raise ValueError(f"Comparison operator {type(op).__name__}")

    async def _human_task_resolved(self, db, run_id: int, step_id: int) -> bool:
        """Check if a human task is resolved (completed or closed). For resume to work properly."""
        stmt = select(Task).where(Task.workflow_run_id == run_id, Task.step_id == step_id)
        result = await db.execute(stmt)
        tasks = result.scalars().all()
        if not tasks:
            # No task found — treat as resolved (no human action needed)
            return True
        return all(t.status in ("completed", "closed") for t in tasks)


# Module-level shared engine instance.
#
# ``tasks.py`` (resume-after-reopen) and ``step_executors.py`` (SubWorkflowExecutor)
# both do ``from app.services.workflow_engine import workflow_engine`` and then call
# e.g. ``workflow_engine.resume_workflow(...)`` / ``workflow_engine.trigger_workflow(...)``.
# This singleton is that name; without it those imports raise ImportError. It is safe
# to build here at import time: ``__init__`` only registers the built-in step executors
# (which import back into this module lazily, inside methods, so there is no
# circular-import cycle), and the engine is effectively stateless across runs -- every
# public method receives its own ``db`` session.
workflow_engine = WorkflowEngine()

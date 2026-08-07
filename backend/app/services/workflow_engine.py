"""
Core workflow engine for executing workflows and steps
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.schemas import Workflow, WorkflowStep, WorkflowRun, StepInstance, Task
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate, WorkflowRunCreate
from app.services.email_service import notify_admin

logger = logging.getLogger(__name__)


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
        }
    
    async def create_workflow(self, db: AsyncSession, workflow_data: WorkflowCreate,
                              created_by: Optional[int] = None,
                              allowed_group_ids: Optional[List[int]] = None) -> Workflow:
        """Create a new workflow"""
        workflow = Workflow(
            name=workflow_data.name,
            description=workflow_data.description,
            version=1,
            config=workflow_data.config or {},
            portal_icon=workflow_data.portal_icon,
            portal_order=workflow_data.portal_order,
            portal_visible=workflow_data.portal_visible,
            created_by=created_by
        )
        db.add(workflow)
        await db.flush()

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
                description=step_data.get("description", "")
            )
            db.add(step)
        
        await db.commit()
        await db.refresh(workflow, attribute_names=["steps"])
        return workflow
    
    async def update_workflow(self, db: AsyncSession, workflow_id: int, workflow_data: WorkflowUpdate) -> Optional[Workflow]:
        """Update an existing workflow"""
        stmt = select(Workflow).where(Workflow.id == workflow_id)
        result = await db.execute(stmt)
        workflow = result.scalar_one_or_none()
        
        if not workflow:
            return None
        
        if workflow_data.name is not None:
            workflow.name = workflow_data.name
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
            if workflow.config is None:
                workflow.config = {}
            workflow.config["portal_link_url"] = workflow_data.portal_link_url
        
        # P7: Manual version increment
        if workflow_data.manual_version_increment:
            workflow.version += 1
        
        # Update steps if provided
        if workflow_data.steps is not None:
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
                    description=step_data.get("description", "")
                )
                db.add(step)
        
        workflow.version += 1
        await db.commit()
        await db.refresh(workflow)
        return workflow
    
    async def delete_workflow(self, db: AsyncSession, workflow_id: int) -> bool:
        """Delete a workflow and all its runs"""
        stmt = select(Workflow).where(Workflow.id == workflow_id)
        result = await db.execute(stmt)
        workflow = result.scalar_one_or_none()
        
        if not workflow:
            return False
        
        await db.delete(workflow)
        await db.commit()
        return True
    
    async def trigger_workflow(self, db: AsyncSession, workflow_id: int, run_data: WorkflowRunCreate) -> WorkflowRun:
        """Trigger a new workflow run"""
        # Get workflow with steps
        stmt = (
            select(Workflow)
            .where(Workflow.id == workflow_id)
            .options(selectinload(Workflow.steps))
        )
        result = await db.execute(stmt)
        workflow = result.scalar_one()
        
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")
        
        if not workflow.is_active:
            raise ValueError(f"Workflow {workflow_id} is not active")
        
        # Create run
        run = WorkflowRun(
            workflow_id=workflow_id,
            status="pending",
            triggered_by=run_data.triggered_by,
            input_data=run_data.input_data,
            timeout_seconds=run_data.timeout_seconds,
            max_retries=run_data.max_retries,
            failure_hooks=run_data.failure_hooks
        )
        db.add(run)
        await db.flush()
        
        # Create step instances
        for step in workflow.steps:
            instance = StepInstance(
                workflow_run_id=run.id,
                step_id=step.id,
                status="pending",
                input_data=run_data.input_data.copy(),
                position=step.position,
                max_retries=step.max_retries or run_data.max_retries
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
        
        elapsed = (datetime.utcnow() - run.started_at).total_seconds()
        if elapsed > run.timeout_seconds:
            run.status = "timeout"
            run.error_message = f"Run timed out after {run.timeout_seconds} seconds (elapsed: {elapsed:.1f}s)"
            run.completed_at = datetime.utcnow()
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
                            await db.commit()
                            continue
                        success = await self._execute_single_step(db, run, instance, step)
                        if not success:
                            break
                else:
                    # Graph mode: follow explicit connections with parallel fan-out
                    await self._execute_branching_sync(db, run, run_id, workflow, step_instances)
                
                if run.status == "running":
                    run.status = "completed"
                    print(f"DEBUG: Set run status to completed")
                
                if run.status in ("completed", "failed"):
                    run.completed_at = datetime.utcnow()
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
                
                output_data = await executor.execute(instance.input_data, step.definition, db=db)
                
                instance.status = "completed"
                instance.output_data = output_data
                instance.completed_at = datetime.utcnow()
                instance.retry_count = 0  # Reset retry count on success
                instance.last_error = ""
                
                # Update run input for next steps
                run.input_data.update(output_data)
                
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
    
    async def _handle_human_step(self, db, run, instance, step) -> bool:
        """Handle human_task or approval steps - create task and pause workflow"""
        definition = step.definition or {}
        
        # Extract assignment info
        assigned_to_user_id = definition.get("assigned_to_user_id")
        assigned_group_id = definition.get("assigned_group_id")
        form_id = definition.get("form_id")
        
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
            task_data=definition.get("task_data", {}),
            result_data={}
        )
        
        db.add(task)
        await db.flush()
        
        # Mark step instance as completed (but workflow pauses here)
        instance.status = "completed"
        instance.output_data = {"task_id": task.id, "status": "pending_human_action"}
        instance.completed_at = datetime.utcnow()
        
        run.input_data.update(instance.output_data)
        # Mark workflow as waiting on human action (resume continues from here)
        run.status = "waiting"
        
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
                        logger.info(f"Updated step instance {instance.id} output with task result")
            
            await db.commit()
            
            logger.info(f"Resuming workflow run {run_id} with {len(step_instances)} step instances")
            
            # Mark run as running and re-execute the workflow (this will pick up where it left off)
            run.status = "running"
            await db.commit()
            await self._execute_workflow(run_id)
    
    async def _execute_branching(self, db, run, run_id: int, workflow: Workflow, step_instances):
        """Execute a workflow following explicit connections, supporting parallel fan-out.
        Each path runs in its own DB session so branches execute concurrently."""
        # This method is kept for backward compatibility but now delegates to the sync version
        await self._execute_branching_sync(db, run, run_id, workflow, step_instances)

    async def _execute_branching_sync(self, db, run, run_id: int, workflow: Workflow, step_instances):
        """Execute a workflow following explicit connections synchronously.
        This avoids session management issues that occur with parallel execution."""
        instance_lookup = {inst.step_id: inst for inst in step_instances}
        step_lookup = {s.id: s for s in workflow.steps}
        visited = set()

        async def execute_path(step_id: int, input_data: dict):
            # Check timeout at the start of each step
            if await self._check_timeout(db, run):
                return
            
            if step_id in visited:
                return
            visited.add(step_id)

            instance = instance_lookup.get(step_id)
            step = step_lookup.get(step_id)
            if not instance or not step:
                return

            # Resume-aware: skip steps that already ran.
            if instance.status in ("completed", "failed", "skipped"):
                # For human steps, check if task is resolved.
                if step.step_type in ("human_task", "approval") and not await self._human_task_resolved(db, run_id, step.id):
                    run.status = "waiting"
                    await db.commit()
                    return
                step_targets = self._get_targets(step, run.input_data)
                valid_targets = [t for t in step_targets if t in instance_lookup and t not in visited]
                for target in valid_targets:
                    await execute_path(target, run.input_data)
                return

            # Skip disabled steps - mark them as skipped but don't execute
            if not step.is_enabled:
                instance.status = "skipped"
                instance.output_data = {"skipped_reason": "step_disabled"}
                instance.completed_at = datetime.utcnow()
                await db.commit()
                # Still get targets so workflow continues past disabled step
                step_targets = self._get_targets(step, input_data)
                valid_targets = [t for t in step_targets if t in instance_lookup and t not in visited]
                for target in valid_targets:
                    await execute_path(target, input_data)
                return

            run.input_data.update(input_data)
            instance.input_data.update(run.input_data)

            success = await self._execute_single_step(db, run, instance, step)
            if not success:
                return
            step_targets = self._get_targets(step, run.input_data)
            valid_targets = [t for t in step_targets if t in instance_lookup and t not in visited]
            for target in valid_targets:
                await execute_path(target, input_data)

        # Entry steps come only from explicit start config (what the designer wired up)
        config = workflow.config or {}
        start_ids = [i for i in config.get("start_step_ids", []) if i in instance_lookup]
        if not start_ids:
            return  # No start outputs configured — nothing to execute

        for sid in start_ids:
            await execute_path(sid, {})

        # Mark any unvisited instances as skipped
        for instance in step_instances:
            if instance.status == "pending" and instance.step_id not in visited:
                instance.status = "skipped"
                instance.completed_at = datetime.utcnow()
        if any(i.status == "skipped" for i in step_instances):
            await db.commit()

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
        """Evaluate a condition expression. Raises ValueError on any error (STRICT)."""
        try:
            return bool(eval(condition_expr, {"__builtins__": {}}, {"data": data}))
        except Exception as e:
            raise ValueError(
                f"Condition evaluation failed for expression {condition_expr!r}: "
                f"{type(e).__name__}: {e}"
            ) from e

    async def _human_task_resolved(self, db, run_id: int, step_id: int) -> bool:
        """Check if a human task is resolved (completed or closed). For resume to work properly."""
        stmt = select(Task).where(Task.workflow_run_id == run_id, Task.step_id == step_id)
        result = await db.execute(stmt)
        tasks = result.scalars().all()
        if not tasks:
            # No task found — treat as resolved (no human action needed)
            return True
        return all(t.status in ("completed", "closed") for t in tasks)

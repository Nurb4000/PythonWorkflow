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

from app.models.schemas import Workflow, WorkflowStep, WorkflowRun, StepInstance
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate, WorkflowRunCreate

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
            DelayExecutor
        )
        
        self.step_executors = {
            "api_call": APICallExecutor(),
            "database_query": DatabaseQueryExecutor(),
            "email": EmailExecutor(),
            "condition": ConditionExecutor(),
            "delay": DelayExecutor(),
        }
    
    async def create_workflow(self, db: AsyncSession, workflow_data: WorkflowCreate) -> Workflow:
        """Create a new workflow"""
        workflow = Workflow(
            name=workflow_data.name,
            description=workflow_data.description,
            version=1
        )
        db.add(workflow)
        await db.flush()
        
        # Create steps
        for i, step_data in enumerate(workflow_data.steps):
            step = WorkflowStep(
                workflow_id=workflow.id,
                step_type=step_data["step_type"],
                definition=step_data.get("definition", {}),
                position=i,
                condition_expr=step_data.get("condition_expr", ""),
                is_enabled=step_data.get("is_enabled", True)
            )
            db.add(step)
        
        await db.commit()
        await db.refresh(workflow)
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
                    is_enabled=step_data.get("is_enabled", True)
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
            input_data=run_data.input_data
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
                position=step.position
            )
            db.add(instance)
        
        await db.commit()
        await db.refresh(run)
        
        # Execute workflow asynchronously
        asyncio.create_task(self._execute_workflow(db, run.id))
        
        return run
    
    async def _execute_workflow(self, db: AsyncSession, run_id: int):
        """Execute a workflow run"""
        try:
            # Get run with step instances
            stmt = (
                select(WorkflowRun)
                .where(WorkflowRun.id == run_id)
                .options(selectinload(WorkflowRun.step_instances))
            )
            result = await db.execute(stmt)
            run = result.scalar_one()
            
            # Update status to running
            run.status = "running"
            run.started_at = datetime.utcnow()
            await db.commit()
            
            # Execute steps in order
            step_instances = sorted(run.step_instances, key=lambda x: x.position)
            
            for instance in step_instances:
                if run.status != "running":
                    break  # Workflow was cancelled
                
                # Check condition
                if instance.status == "pending":
                    step_stmt = select(WorkflowStep).where(WorkflowStep.id == instance.step_id)
                    step_result = await db.execute(step_stmt)
                    step = step_result.scalar_one()
                    
                    if step.condition_expr and not self._evaluate_condition(step.condition_expr, instance.input_data):
                        instance.status = "skipped"
                        instance.completed_at = datetime.utcnow()
                        continue
                
                # Execute step
                try:
                    instance.status = "running"
                    instance.started_at = datetime.utcnow()
                    await db.commit()
                    
                    executor = self.step_executors.get(step.step_type)
                    if not executor:
                        raise ValueError(f"No executor for step type: {step.step_type}")
                    
                    output_data = await executor.execute(instance.input_data, step.definition)
                    
                    instance.status = "completed"
                    instance.output_data = output_data
                    instance.completed_at = datetime.utcnow()
                    
                    # Update run input for next steps
                    run.input_data.update(output_data)
                    
                except Exception as e:
                    logger.error(f"Step {instance.id} failed: {str(e)}")
                    instance.status = "failed"
                    instance.error_message = str(e)
                    instance.completed_at = datetime.utcnow()
                    
                    run.status = "failed"
                    run.error_message = f"Step {instance.id} failed: {str(e)}"
                    break
                
                await db.commit()
            
            if run.status == "running":
                run.status = "completed"
            
            run.completed_at = datetime.utcnow()
            run.output_data = run.input_data.copy()
            await db.commit()
            
        except Exception as e:
            logger.error(f"Workflow run {run_id} failed: {str(e)}")
            try:
                run_stmt = select(WorkflowRun).where(WorkflowRun.id == run_id)
                run_result = await db.execute(run_stmt)
                run = run_result.scalar_one()
                run.status = "failed"
                run.error_message = str(e)
                run.completed_at = datetime.utcnow()
                await db.commit()
            except:
                pass
    
    def _evaluate_condition(self, condition_expr: str, data: Dict[str, Any]) -> bool:
        """Evaluate a condition expression"""
        try:
            # Simple condition evaluation (can be enhanced later)
            # For now, support basic Python expressions
            return eval(condition_expr, {"__builtins__": {}}, {"data": data})
        except:
            return True  # Default to true if evaluation fails

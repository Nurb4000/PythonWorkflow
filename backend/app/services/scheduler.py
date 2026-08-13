"""
Enhanced scheduler service with webhook and external trigger support
"""
import logging
from typing import Dict, Any, Optional, List
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.schemas import Workflow, WorkflowRun, Schedule
from app.models.services import Service
from app.services.workflow_engine import WorkflowEngine
from app.schemas.workflow import WorkflowRunCreate

logger = logging.getLogger(__name__)


class SchedulerService:
    """Manage workflow scheduling and triggers"""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.engine = WorkflowEngine()
        self._initialized = False
        self.db_session_factory = None
    
    async def initialize(self, db_session_factory):
        """Initialize scheduler with existing schedules"""
        self.db_session_factory = db_session_factory
        
        # Load existing schedules from database
        async with db_session_factory() as db:
            stmt = select(Schedule).where(Schedule.is_enabled == True)
            result = await db.execute(stmt)
            schedules = result.scalars().all()
            
            for schedule in schedules:
                self._add_schedule_job(schedule)
        
        self._initialized = True
        self.scheduler.start()

        # SLA breach monitoring job (Phase 5) — runs every 15 minutes
        self.scheduler.add_job(
            self._check_sla_breaches,
            trigger=IntervalTrigger(minutes=15),
            id="sla_breach_monitor",
            replace_existing=True,
        )
        logger.info(f"Scheduler initialized with {len(schedules)} schedules + SLA monitor")
    
    def _add_schedule_job(self, schedule: Schedule):
        """Add a scheduled workflow run job"""
        
        async def run_workflow():
            """Async function to run the workflow"""
            async with self.db_session_factory() as db:
                try:
                    # Get workflow
                    stmt = select(Workflow).where(Workflow.id == schedule.workflow_id)
                    result = await db.execute(stmt)
                    workflow = result.scalar_one_or_none()
                    
                    if not workflow or not workflow.is_active:
                        logger.warning(f"Workflow {schedule.workflow_id} not found or inactive")
                        return
                    
                    # Trigger run
                    run_data = WorkflowRunCreate(triggered_by="schedule")
                    run = await self.engine.trigger_workflow(db, workflow.id, run_data)
                    
                    # Update schedule
                    schedule.last_run_at = datetime.utcnow()
                    await db.commit()
                    
                    logger.info(f"Scheduled workflow {workflow.id} run {run.id}")
                    
                except Exception as e:
                    logger.error(f"Scheduled run failed: {str(e)}")
        
        # Create trigger based on cron expression
        try:
            parts = schedule.cron_expression.split()
            if len(parts) == 5:
                trigger = CronTrigger(
                    minute=parts[0],
                    hour=parts[1],
                    day=parts[2],
                    month=parts[3],
                    day_of_week=parts[4]
                )
                
                self.scheduler.add_job(
                    run_workflow,
                    trigger=trigger,
                    id=f"schedule_{schedule.id}",
                    replace_existing=True
                )
                
                # Calculate next run time
                next_run = trigger.get_next_fire_time(None, datetime.utcnow())
                schedule.next_run_at = next_run
                
            logger.info(f"Added schedule job for workflow {schedule.workflow_id}")
            
        except Exception as e:
            logger.error(f"Failed to add schedule job: {str(e)}")
    
    def add_schedule(self, schedule: Schedule):
        """Add a new schedule"""
        self._add_schedule_job(schedule)
    
    def remove_schedule(self, schedule_id: int):
        """Remove a schedule job"""
        job_id = f"schedule_{schedule_id}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed schedule job {job_id}")
    
    def update_schedule(self, schedule: Schedule):
        """Update an existing schedule"""
        self.remove_schedule(schedule.id)
        self._add_schedule_job(schedule)
    
    async def trigger_webhook(self, workflow_id: int, payload: Dict[str, Any], auth_token: Optional[str] = None) -> WorkflowRun:
        """Trigger a workflow via webhook"""
        
        async with self.db_session_factory() as db:
            # Verify workflow exists and is active
            stmt = select(Workflow).where(Workflow.id == workflow_id)
            result = await db.execute(stmt)
            workflow = result.scalar_one_or_none()
            
            if not workflow:
                raise ValueError(f"Workflow {workflow_id} not found")
            
            if not workflow.is_active:
                raise ValueError(f"Workflow {workflow_id} is not active")
            
            # Create run with webhook data
            run_data = WorkflowRunCreate(
                input_data=payload,
                triggered_by="webhook"
            )
            run = await self.engine.trigger_workflow(db, workflow_id, run_data)
            
            logger.info(f"Webhook triggered workflow {workflow_id} run {run.id}")
            return run
    
    async def trigger_external_api(self, workflow_id: int, input_data: Dict[str, Any], 
                                    api_key: Optional[str] = None) -> WorkflowRun:
        """Trigger a workflow via external API"""
        
        async with self.db_session_factory() as db:
            # Verify workflow exists and is active
            stmt = select(Workflow).where(Workflow.id == workflow_id)
            result = await db.execute(stmt)
            workflow = result.scalar_one_or_none()
            
            if not workflow:
                raise ValueError(f"Workflow {workflow_id} not found")
            
            if not workflow.is_active:
                raise ValueError(f"Workflow {workflow_id} is not active")
            
            # Create run with external data
            run_data = WorkflowRunCreate(
                input_data=input_data,
                triggered_by="api"
            )
            run = await self.engine.trigger_workflow(db, workflow_id, run_data)
            
            logger.info(f"External API triggered workflow {workflow_id} run {run.id}")
            return run
    
    def get_active_schedules(self) -> List[Dict[str, Any]]:
        """Get all active schedules with their next run times"""
        schedules = []
        
        for job in self.scheduler.get_jobs():
            schedule_id = int(job.id.replace("schedule_", ""))
            next_run = job.next_run_time
            
            schedules.append({
                "id": schedule_id,
                "next_run_at": next_run,
                "job_id": job.id
            })
        
        return schedules
    
    async def _check_sla_breaches(self):
        """Periodic job: check for SLA breaches and send notifications."""
        if not self.db_session_factory:
            return

        from datetime import timezone as tz
        from app.services.email_service import notify_admin

        async with self.db_session_factory() as db:
            try:
                # Find running/waiting/pending runs with SLA targets that haven't been evaluated yet
                stmt = select(WorkflowRun).where(
                    WorkflowRun.status.in_(["running", "waiting", "pending"]),
                    WorkflowRun.sla_response_target_hours.isnot(None),
                    WorkflowRun.sla_response_met.is_(None),
                )
                result = await db.execute(stmt)
                runs = result.scalars().all()

                now = datetime.now(tz.utc)
                breached_ids = []

                for run in runs:
                    if not run.started_at:
                        continue

                    start = run.started_at.replace(tzinfo=tz.utc) if run.started_at.tzinfo is None else run.started_at
                    elapsed_hours = (now - start).total_seconds() / 3600
                    target_hours = run.sla_response_target_hours

                    # Check if breached (>100% of target)
                    if elapsed_hours >= target_hours:
                        run.sla_response_met = False
                        breached_ids.append(run.id)

                        # Get service name for notification
                        svc_name = f"Run #{run.id}"
                        if run.service_id:
                            svc_stmt = select(Service.name).where(Service.id == run.service_id)
                            svc_result = await db.execute(svc_stmt)
                            svc_row = svc_result.scalar_one_or_none()
                            if svc_row:
                                svc_name = f"{svc_row} (Run #{run.id})"

                        notify_admin(
                            f"SLA Response Breach: {svc_name}",
                            (
                                f"Workflow run #{run.id} has breached its response SLA.\n\n"
                                f"Workflow: {run.workflow_name}\n"
                                f"Priority: {run.priority}\n"
                                f"Target: {target_hours}h\n"
                                f"Elapsed: {elapsed_hours:.1f}h\n"
                                f"Status: {run.status}\n"
                                f"Started: {run.started_at.isoformat()}"
                            )
                        )

                    # Check if approaching breach (>=80% of target) — log warning only
                    elif elapsed_hours >= target_hours * 0.8:
                        logger.warning(
                            f"SLA Response approaching breach for run #{run.id}: "
                            f"{elapsed_hours:.1f}h / {target_hours}h target ({elapsed_hours/target_hours*100:.0f}%)"
                        )

                if breached_ids:
                    await db.commit()
                    logger.info(f"SLA monitor: marked {len(breached_ids)} run(s) as response breached")

            except Exception as e:
                logger.error(f"SLA breach check failed: {e}")

    def stop(self):
        """Stop the scheduler and email monitor"""
        self.stop_email_monitor()
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped")

    # ------------------------------------------------------------------
    # Email monitor integration
    # ------------------------------------------------------------------

    async def start_email_monitor(self):
        """Start the IMAP email polling job based on admin settings."""
        from app.services.email_monitor import email_monitor
        await email_monitor._load_settings()
        email_monitor.start_polling()

    def stop_email_monitor(self):
        """Stop the IMAP email polling job."""
        from app.services.email_monitor import email_monitor
        email_monitor.stop_polling()
        email_monitor.disconnect()

    def restart_email_monitor(self):
        """Restart polling with updated settings (called after admin changes settings)."""
        from app.services.email_monitor import email_monitor
        email_monitor.restart_polling()


# Global scheduler instance
scheduler_service = SchedulerService()

"""
Database models for the workflow system
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey, Boolean, Table, Index, text as sa_text, text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

# Import association table from auth models
from app.models.auth import workflow_permissions

# Lazy import for Form to avoid circular imports
# from app.models.forms import Form  # Imported below when needed


class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, default="")
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # A3: explicit owner
    tags = Column(JSON, default=list)  # A3: freeform tags for organization
    is_published = Column(Boolean, default=False)
    environment = Column(String(20), default="test")
    config = Column(JSON, default=dict)  # Workflow-level config (e.g. start_step_ids)
    portal_icon = Column(String(20), default="", server_default="")  # Emoji/short icon for portal cards
    portal_order = Column(Integer, default=0, server_default="0")  # Sort order on the portal
    portal_visible = Column(Boolean, default=True, server_default=sa_text("true"))  # Show on the portal
    show_in_portal = Column(Boolean, default=True, server_default=sa_text("true"))  # Show on general Offerings page (vs service-only)
    entry_form_id = Column(Integer, nullable=True)  # Form to show before triggering (P3.3)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=True)  # SERVICE_MANAGEMENT_PLAN Phase 1
    is_deprecated = Column(Boolean, default=False)  # E1: deprecation state
    deprecated_at = Column(DateTime(timezone=True), nullable=True)  # E1
    deprecated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # E1
    suggested_replacement_id = Column(Integer, ForeignKey("workflows.id"), nullable=True)  # E1
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    steps = relationship("WorkflowStep", back_populates="workflow", cascade="all, delete-orphan", order_by="WorkflowStep.position")
    runs = relationship("WorkflowRun", back_populates="workflow")
    allowed_groups = relationship("Group", secondary=workflow_permissions, back_populates="workflows")
    service = relationship("Service", back_populates="workflows")
    # entry_form relationship can be added later if needed (avoids circular import)


class WorkflowStep(Base):
    __tablename__ = "workflow_steps"

    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"), nullable=False)
    step_type = Column(String(50), nullable=False)  # api_call, database_query, email, form, condition, etc.
    definition = Column(JSON, nullable=False)  # Step configuration
    position = Column(Integer, default=0)  # Order in workflow
    condition_expr = Column(Text, default="")  # Conditional execution expression
    is_enabled = Column(Boolean, default=True)
    title = Column(String(255), default="", server_default="")  # User-friendly title for this step
    description = Column(Text, default="", server_default="")  # Description of what this step does
    max_retries = Column(Integer, default=0)  # Maximum retries for this step (0 = use run default)
    retry_delay_seconds = Column(Integer, default=0)  # Delay between retries
    failure_hook_url = Column(String(500), default="")  # URL to call on failure
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    workflow = relationship("Workflow", back_populates="steps")
    instances = relationship("StepInstance", back_populates="step")


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(20), default="pending")  # pending, running, completed, failed, cancelled, waiting, timeout
    triggered_by = Column(String(100), default="manual")  # manual, schedule, api, webhook
    workflow_name = Column(String(255), default="", server_default="")  # Snapshot of the workflow name at run creation
    input_data = Column(JSON, default=dict)  # Initial input data
    output_data = Column(JSON, default=dict)  # Final output data
    error_message = Column(Text, default="")
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    timeout_seconds = Column(Integer, default=0)  # 0 means no timeout
    retry_count = Column(Integer, default=0)  # Current retry count for the run
    max_retries = Column(Integer, default=0)  # Maximum retries per step (0 = no retries)
    failure_hooks = Column(JSON, default=list)  # List of failure hook URLs/configs
    custom_data = Column(JSON, default=dict)  # Custom field extensions
    priority = Column(Integer, nullable=True)  # SERVICE_MANAGEMENT_PLAN Phase 3: priority level ID
    service_id = Column(Integer, ForeignKey("services.id"), nullable=True)  # SERVICE_MANAGEMENT_PLAN Phase 4: track service on run
    sla_response_target_hours = Column(Integer, nullable=True)  # SERVICE_MANAGEMENT_PLAN Phase 5
    sla_resolution_target_hours = Column(Integer, nullable=True)  # SERVICE_MANAGEMENT_PLAN Phase 5
    sla_response_met = Column(Boolean, nullable=True)  # SERVICE_MANAGEMENT_PLAN Phase 5: True=met, False=breached, None=not yet evaluated
    sla_resolution_met = Column(Boolean, nullable=True)  # SERVICE_MANAGEMENT_PLAN Phase 5
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    workflow = relationship("Workflow", back_populates="runs")
    step_instances = relationship("StepInstance", back_populates="workflow_run", cascade="all, delete-orphan")


class StepInstance(Base):
    __tablename__ = "step_instances"

    id = Column(Integer, primary_key=True, index=True)
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"), nullable=False)
    step_id = Column(Integer, ForeignKey("workflow_steps.id", ondelete="SET NULL"), nullable=True)
    step_title = Column(String(255), default="", server_default="")  # Snapshot of step title at run time
    step_type = Column(String(50), default="", server_default="")  # Snapshot of step type at run time
    step_description = Column(Text, default="", server_default="")  # Snapshot of step description
    step_definition = Column(JSON, nullable=True)  # Snapshot of step definition at run time
    status = Column(String(20), default="pending")  # pending, running, completed, failed, skipped
    input_data = Column(JSON, default=dict)
    output_data = Column(JSON, default=dict)
    error_message = Column(Text, default="")
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    position = Column(Integer, default=0)
    retry_count = Column(Integer, default=0)  # Current retry count for this instance
    max_retries = Column(Integer, default=0)  # Maximum retries for this instance
    last_error = Column(Text, default="")  # Last error message for retry
    custom_data = Column(JSON, default=dict)  # Custom field extensions

    # Relationships
    workflow_run = relationship("WorkflowRun", back_populates="step_instances")
    step = relationship("WorkflowStep", back_populates="instances")

    @property
    def title(self):
        """Best-available step title (snapshot first, then type)."""
        return self.step_title or self.step_type or ""

    @property
    def description(self):
        return self.step_description or ""

    @property
    def route_taken(self):
        """Target step ids this instance routed to (recorded at execution)."""
        return list((self.custom_data or {}).get("route_taken") or [])

    @property
    def duration_seconds(self):
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class Task(Base):
    __tablename__ = "tasks"

    __table_args__ = (
        Index("idx_tasks_status", "status"),
        Index("idx_tasks_assigned_user", "assigned_to_user_id"),
        Index("idx_tasks_workflow_run", "workflow_run_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"), nullable=True)
    step_id = Column(Integer, ForeignKey("workflow_steps.id"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, default="")
    status = Column(String(50), default="open")  # open, review, owned, completed, closed
    assigned_to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    assigned_group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)
    form_id = Column(Integer, nullable=True)
    task_data = Column(JSON, default=dict)
    result_data = Column(JSON, default=dict)
    custom_data = Column(JSON, default=dict)  # Custom field extensions
    priority = Column(Integer, nullable=True)  # OLA: inherited from workflow run priority
    ola_pickup_target_hours = Column(Integer, nullable=True)  # OLA: target for task to be taken
    ola_closure_target_hours = Column(Integer, nullable=True)  # OLA: target for task to be completed/closed
    ola_pickup_met = Column(Boolean, nullable=True)  # OLA: True=met, False=breached, None=pending
    ola_closure_met = Column(Boolean, nullable=True)  # OLA: True=met, False=breached, None=pending
    pause_state = Column(String(50), default="in_process")  # SLA/OLA pause states
    is_active = Column(Boolean, default=True, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True))
    closed_at = Column(DateTime(timezone=True))

    # Relationships
    workflow_run = relationship("WorkflowRun", backref="tasks")
    step = relationship("WorkflowStep", backref="tasks")
    assigned_user = relationship("User", foreign_keys=[assigned_to_user_id])
    assigned_group = relationship("Group", foreign_keys=[assigned_group_id])


class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"), nullable=False)
    cron_expression = Column(String(100), nullable=False)
    is_enabled = Column(Boolean, default=True)
    last_run_at = Column(DateTime(timezone=True))
    next_run_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    workflow = relationship("Workflow")

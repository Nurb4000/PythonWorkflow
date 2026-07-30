"""
Database models for the workflow system
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey, Boolean, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

# Import association table from auth models
from app.models.auth import workflow_permissions


class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, default="")
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_published = Column(Boolean, default=False)
    environment = Column(String(20), default="test")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    steps = relationship("WorkflowStep", back_populates="workflow", cascade="all, delete-orphan")
    runs = relationship("WorkflowRun", back_populates="workflow", cascade="all, delete-orphan")
    allowed_groups = relationship("Group", secondary=workflow_permissions, back_populates="workflows")


class WorkflowStep(Base):
    __tablename__ = "workflow_steps"

    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"), nullable=False)
    step_type = Column(String(50), nullable=False)  # api_call, database_query, email, form, condition, etc.
    definition = Column(JSON, nullable=False)  # Step configuration
    position = Column(Integer, default=0)  # Order in workflow
    condition_expr = Column(Text, default="")  # Conditional execution expression
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    workflow = relationship("Workflow", back_populates="steps")
    instances = relationship("StepInstance", back_populates="step", cascade="all, delete-orphan")


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"), nullable=False)
    status = Column(String(20), default="pending")  # pending, running, completed, failed, cancelled
    triggered_by = Column(String(100), default="manual")  # manual, schedule, api, webhook
    input_data = Column(JSON, default=dict)  # Initial input data
    output_data = Column(JSON, default=dict)  # Final output data
    error_message = Column(Text, default="")
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    workflow = relationship("Workflow", back_populates="runs")
    step_instances = relationship("StepInstance", back_populates="workflow_run", cascade="all, delete-orphan")


class StepInstance(Base):
    __tablename__ = "step_instances"

    id = Column(Integer, primary_key=True, index=True)
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"), nullable=False)
    step_id = Column(Integer, ForeignKey("workflow_steps.id"), nullable=False)
    status = Column(String(20), default="pending")  # pending, running, completed, failed, skipped
    input_data = Column(JSON, default=dict)
    output_data = Column(JSON, default=dict)
    error_message = Column(Text, default="")
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    position = Column(Integer, default=0)

    # Relationships
    workflow_run = relationship("WorkflowRun", back_populates="step_instances")
    step = relationship("WorkflowStep", back_populates="instances")


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

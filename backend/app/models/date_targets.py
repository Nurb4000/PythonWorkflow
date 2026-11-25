"""
Date-based target tracking for workflow runs and tasks.

Unlike SLA/OLA which track elapsed hours from creation, date_targets track
absolute calendar deadlines (e.g., change implementation must complete by
2026-09-01 06:00). Used by change management workflows and any flow that
needs a hard deadline rather than a relative time window.
"""
from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Boolean, Index, text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class DateTarget(Base):
    __tablename__ = "date_targets"

    id = Column(Integer, primary_key=True, index=True)
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    step_id = Column(Integer, ForeignKey("workflow_steps.id", ondelete="SET NULL"), nullable=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    target_key = Column(String(100), nullable=False, index=True)
    target_datetime = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(String(20), default="pending")
    is_active = Column(Boolean, default=True, server_default=text("true"))
    custom_data = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_date_targets_status_pending", "status", "target_datetime"),
    )

    # Relationships
    workflow_run = relationship("WorkflowRun")
    step = relationship("WorkflowStep")
    task = relationship("Task")

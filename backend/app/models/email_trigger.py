"""
Email trigger models - tracking processed emails and preventing duplicates
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class EmailProcessingLog(Base):
    """Tracks each email processed by the IMAP monitor to prevent reprocessing."""
    __tablename__ = "email_processing_log"

    id = Column(Integer, primary_key=True, index=True)
    email_uid = Column(String(100), nullable=False, index=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"), nullable=True)
    run_id = Column(Integer, ForeignKey("workflow_runs.id"), nullable=True)
    email_from = Column(String(500), default="")
    email_subject = Column(Text, default="")
    rule_tag = Column(String(50), default="")
    status = Column(String(20), default="pending")
    error_message = Column(Text, default="")
    processed_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_email_uid_workflow", "email_uid", "workflow_id"),
    )

    workflow = relationship("Workflow", foreign_keys=[workflow_id])
    run = relationship("WorkflowRun", foreign_keys=[run_id])

"""
Form management models and service
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class Form(Base):
    __tablename__ = "forms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    schema_json = Column(JSON, nullable=False)  # JSON Schema definition
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    environment = Column(String(20), default="test")  # test, production
    is_published = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    submissions = relationship("FormSubmission", back_populates="form", cascade="all, delete-orphan")


class FormSubmission(Base):
    __tablename__ = "form_submissions"

    id = Column(Integer, primary_key=True, index=True)
    form_id = Column(Integer, ForeignKey("forms.id"), nullable=False)
    submitted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    data = Column(JSON, nullable=False)  # Submitted form data
    status = Column(String(20), default="submitted")  # submitted, approved, rejected
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    form = relationship("Form", back_populates="submissions")
    user = relationship("User")
    workflow_run = relationship("WorkflowRun")


class FormTemplate(Base):
    __tablename__ = "form_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    schema_json = Column(JSON, nullable=False)
    category = Column(String(100))  # contact, registration, feedback, etc.
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

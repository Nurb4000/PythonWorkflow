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
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # A3: explicit owner
    tags = Column(JSON, default=list)  # A3: freeform tags for organization
    environment = Column(String(20), default="test")  # test, production
    is_published = Column(Boolean, default=False)
    is_deprecated = Column(Boolean, default=False)  # E1: deprecation state
    deprecated_at = Column(DateTime(timezone=True), nullable=True)  # E1
    deprecated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # E1
    suggested_replacement_id = Column(Integer, ForeignKey("forms.id"), nullable=True)  # E1
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
    custom_data = Column(JSON, default=dict)  # Custom field extensions
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    form = relationship("Form", back_populates="submissions")
    user = relationship("User")
    workflow_run = relationship("WorkflowRun")


class FormUpload(Base):
    __tablename__ = "form_uploads"

    id = Column(Integer, primary_key=True, index=True)
    original_name = Column(String(255), nullable=False)
    stored_name = Column(String(255), nullable=False, unique=True, index=True)  # uuid_<original_name>
    content_type = Column(String(255), default="")
    size_bytes = Column(Integer, default=0)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    uploader = relationship("User", foreign_keys=[uploaded_by])


class FormTemplate(Base):
    __tablename__ = "form_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    schema_json = Column(JSON, nullable=False)
    category = Column(String(100))  # contact, registration, feedback, etc.
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

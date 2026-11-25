"""
C1: Shared Field Library — canonical field definitions.

A FieldDefinition is a reusable field template that forms and CI types can
reference via `field_def_id`. The library provides a single source of truth
for field metadata (label, type, options, validation) across the platform.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON, ForeignKey, func
from sqlalchemy.orm import relationship
from app.core.database import Base


class FieldDefinition(Base):
    __tablename__ = "field_definitions"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)  # slug, e.g. "cost_center"
    label = Column(String(255), nullable=False)
    description = Column(Text, default="")
    field_type = Column(String(50), nullable=False, default="string")
    options = Column(JSON, default=list)  # For select/radio: [{"value": "...", "label": "..."}]
    validation_rules = Column(JSON, default=dict)  # {min_length, max_length, pattern, min, max, etc.}
    help_text = Column(Text, default="")
    
    # Ownership (A3)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    tags = Column(JSON, default=list)
    
    # Lifecycle
    is_active = Column(Boolean, default=True)
    is_deprecated = Column(Boolean, default=False)
    deprecated_at = Column(DateTime(timezone=True), nullable=True)
    deprecated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    owner = relationship("User", foreign_keys=[owner_user_id])
    deprecated_by = relationship("User", foreign_keys=[deprecated_by_id])

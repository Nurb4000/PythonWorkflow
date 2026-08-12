"""
Service Management models — Phase 1 of SERVICE_MANAGEMENT_PLAN
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    key = Column(String(255), unique=True, nullable=False, index=True)
    icon = Column(String(10), default="", server_default="")
    description = Column(Text, default="")
    sort_order = Column(Integer, default=0, server_default="0")
    is_active = Column(Boolean, default=True, server_default=func.true())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    services = relationship("Service", back_populates="category")


class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    key = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text, default="")
    icon = Column(String(10), default="", server_default="")
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    support_group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)
    is_active = Column(Boolean, default=True, server_default=func.true())
    sort_order = Column(Integer, default=0, server_default="0")
    custom_data = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    category = relationship("Category", back_populates="services")
    owner = relationship("User")
    support_group = relationship("Group", foreign_keys=[support_group_id])
    workflows = relationship("Workflow", back_populates="service")

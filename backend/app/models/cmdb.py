"""
CMDB models — Configuration Item Types, Items, and Relationships.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class CIType(Base):
    """Configuration Item Type — defines a category of assets (Server, Network Device, etc.)"""
    __tablename__ = "ci_types"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    key = Column(String(50), nullable=False, unique=True, index=True)
    description = Column(Text, default="")
    icon = Column(String(50), default="")
    field_schema = Column(JSON, default=list)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    items = relationship("ConfigurationItem", back_populates="ci_type", cascade="all, delete-orphan")


class ConfigurationItem(Base):
    """Individual CI record — an instance of a CIType."""
    __tablename__ = "configuration_items"

    __table_args__ = (
        Index("idx_configuration_items_type_status", "type_id", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    type_id = Column(Integer, ForeignKey("ci_types.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False, index=True)
    status = Column(String(30), default="active")
    is_active = Column(Boolean, default=True, server_default=func.true())
    ci_data = Column(JSON, default=dict)
    custom_data = Column(JSON, default=dict)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    ci_type = relationship("CIType", back_populates="items")
    source_relationships = relationship(
        "CIRelationship", back_populates="source_ci",
        foreign_keys="CIRelationship.source_ci_id", cascade="all, delete-orphan"
    )
    target_relationships = relationship(
        "CIRelationship", back_populates="target_ci",
        foreign_keys="CIRelationship.target_ci_id"
    )
    history = relationship(
        "CIHistory", back_populates="ci", cascade="all, delete-orphan"
    )


class CIRelationship(Base):
    """Links between CIs — e.g. 'runs_on', 'depends_on', 'part_of'."""
    __tablename__ = "ci_relationships"

    __table_args__ = (
        Index("idx_ci_relationships_source", "source_ci_id"),
        Index("idx_ci_relationships_target", "target_ci_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    source_ci_id = Column(Integer, ForeignKey("configuration_items.id", ondelete="CASCADE"), nullable=False)
    target_ci_id = Column(Integer, ForeignKey("configuration_items.id", ondelete="CASCADE"), nullable=False)
    relationship_type = Column(String(50), nullable=False)
    description = Column(Text, default="")
    is_active = Column(Boolean, default=True, server_default=func.true())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    source_ci = relationship(
        "ConfigurationItem", foreign_keys=[source_ci_id], back_populates="source_relationships"
    )
    target_ci = relationship(
        "ConfigurationItem", foreign_keys=[target_ci_id], back_populates="target_relationships"
    )


class CIHistory(Base):
    """Audit trail for CI changes — tracks field-level modifications."""
    __tablename__ = "ci_history"

    __table_args__ = (
        Index("idx_ci_history_ci_id", "ci_id"),
        Index("idx_ci_history_changed_at", "changed_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    ci_id = Column(Integer, ForeignKey("configuration_items.id", ondelete="CASCADE"), nullable=False, index=True)
    changed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())
    field_key = Column(String(100), nullable=True)
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    change_type = Column(String(20), nullable=False, default="update")

    ci = relationship("ConfigurationItem", back_populates="history")

"""
Marketplace models — reusable workflow packages and node templates.
"""
import json as _json
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class MarketplaceItem(Base):
    __tablename__ = "marketplace_items"

    id = Column(Integer, primary_key=True, index=True)
    item_type = Column(String(20), nullable=False)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, default="")
    category = Column(String(100), default="General")
    tags = Column(Text, default="[]")
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    version = Column(Integer, default=1)
    content = Column(Text, nullable=False)
    content_format = Column(String(10), nullable=False)
    node_type = Column(String(50), nullable=True)
    status = Column(String(20), default="published")
    is_active = Column(Boolean, default=True)
    downloads_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    author = relationship("User", foreign_keys=[author_id])

    __table_args__ = (
        Index("idx_marketplace_items_type_status", "item_type", "status"),
        Index("idx_marketplace_items_category", "category"),
        Index("idx_marketplace_items_author", "author_id"),
    )

    @property
    def tags_list(self):
        try:
            return _json.loads(self.tags) if self.tags else []
        except (ValueError, TypeError):
            return []

    @tags_list.setter
    def tags_list(self, value):
        self.tags = _json.dumps(value) if value else "[]"


class SavedNodeTemplate(Base):
    __tablename__ = "saved_node_templates"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    step_type = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, default="")
    definition = Column(Text, nullable=False)
    condition_expr = Column(Text, default="")
    is_enabled = Column(Boolean, default=True)
    max_retries = Column(Integer, default=0)
    retry_delay_seconds = Column(Integer, default=0)
    failure_hook_url = Column(String(500), default="")
    source_marketplace_item_id = Column(Integer, ForeignKey("marketplace_items.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", foreign_keys=[user_id])
    source_item = relationship("MarketplaceItem", foreign_keys=[source_marketplace_item_id])

    __table_args__ = (
        Index("idx_saved_node_templates_user_step", "user_id", "step_type"),
    )

    @property
    def definition_dict(self):
        try:
            return _json.loads(self.definition) if self.definition else {}
        except (ValueError, TypeError):
            return {}

    @definition_dict.setter
    def definition_dict(self, value):
        self.definition = _json.dumps(value) if value else "{}"

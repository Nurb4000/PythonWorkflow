"""
Multi-tenancy foundation (Feature-Plan §3.1 / gap 3.7).

Shared-schema, column-level tenant isolation. A ``Tenant`` (a.k.a. organization) is
the isolation boundary: every tenant-owned row carries a ``tenant_id``, and queries
are scoped to the current user's tenant. See ``app/services/tenant_scoping.py`` for
the scoping helper and ``app/api/tenancy.py`` for tenant provisioning endpoints.
"""
from sqlalchemy import Boolean, Column, DateTime, Integer, String, func
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.auth import user_tenants


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    slug = Column(String(120), unique=True, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships (resolved lazily by name once all models are loaded).
    users = relationship("User", back_populates="tenant")  # one-to-many via User.tenant_id
    members = relationship(
        "User",
        secondary=user_tenants,
        back_populates="tenants",
    )  # many-to-many: all users who are members of this tenant
    groups = relationship("Group", back_populates="tenant")

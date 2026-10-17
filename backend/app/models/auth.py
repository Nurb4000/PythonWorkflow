"""
User authentication and authorization models
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Table, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

# Association tables for many-to-many relationships
user_groups = Table(
    'user_groups',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('group_id', Integer, ForeignKey('groups.id'), primary_key=True)
)

workflow_permissions = Table(
    'workflow_permissions',
    Base.metadata,
    Column('workflow_id', Integer, ForeignKey('workflows.id'), primary_key=True),
    Column('group_id', Integer, ForeignKey('groups.id'), primary_key=True)
)

kb_article_permissions = Table(
    'kb_article_permissions',
    Base.metadata,
    Column('article_id', Integer, ForeignKey('knowledge_base_articles.id'), primary_key=True),
    Column('group_id', Integer, ForeignKey('groups.id'), primary_key=True)
)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255))
    role = Column(String(20), nullable=False, default="user")  # Primary role (admin, developer, cmdb_manager, staff, user) — kept for backward compat
    roles = Column(JSON, default=list)  # Multiple roles per user (e.g., ["user", "developer"])
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    mfa_enabled = Column(Boolean, default=False)
    ldap_dn = Column(String(500))  # For LDAP integration
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_login = Column(DateTime(timezone=True))
    custom_data = Column(JSON, default=dict)  # Custom field extensions

    # Relationships (defined after all models are loaded)
    groups = relationship("Group", secondary=user_groups, back_populates="users")
    audit_logs = relationship("AuditLog", back_populates="user")


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(500))
    group_type = Column(String(50), default="internal")  # internal, ldap, custom
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    custom_data = Column(JSON, default=dict)  # Custom field extensions

    # Relationships
    users = relationship("User", secondary=user_groups, back_populates="groups")
    workflows = relationship("Workflow", secondary=workflow_permissions, back_populates="allowed_groups")





class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)  # login, create_workflow, run_workflow, etc.
    resource_type = Column(String(50))  # workflow, user, schedule, etc.
    resource_id = Column(Integer)
    details = Column(String(1000))
    ip_address = Column(String(45))
    user_agent = Column(String(500))
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="audit_logs")


class APIToken(Base):
    __tablename__ = "api_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    token_hash = Column(String(255), nullable=False, unique=True)
    permissions = Column(String(500))  # JSON string of allowed actions
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime(timezone=True))
    last_used_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User")


class TokenRevocation(Base):
    """Server-side revocation blocklist for JWT access tokens.

    Stateless JWTs can't be un-issued, so a logged-out (or rotated) token's
    ``jti`` is recorded here and rejected by ``auth_service.verify_token`` until
    the token's ``exp`` passes. Mirrors the DB-backed approach used by
    :class:`APIToken`; no external cache/Redis dependency.
    """

    __tablename__ = "token_revocations"

    id = Column(Integer, primary_key=True)
    jti = Column(String(64), nullable=False, unique=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reason = Column(String(255), nullable=True)
    revoked_at = Column(DateTime(timezone=True), server_default=func.now())

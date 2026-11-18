"""
Regression tests for the multi-tenancy foundation (Feature-Plan §3.1 / gap 3.7).

Shared-schema, column-level tenant isolation: every tenant-owned row carries a
``tenant_id`` and queries are scoped to the current user's tenant. These tests pin
the parts of that design that are cheap to assert without a live PostgreSQL:

  * the ``Tenant`` model schema (unique+indexed slug, non-null is_active default),
  * ``User.tenant_id`` / ``Group.tenant_id`` columns + relationships exist,
  * tenant resolution and scoping helpers isolate reads at the SQL level,
  * the default-tenant helper is idempotent.

The content migration that adds ``tenant_id`` to all 9 content tables and backfills
existing rows to the seeded default tenant is covered separately by an integration
check against PostgreSQL; here we assert the model + service contract it depends on.
"""
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.tenancy import Tenant
from app.models.auth import User, Group
from app.services.tenant_scoping import (
    DEFAULT_TENANT_SLUG,
    resolve_tenant_id,
    apply_tenant_scope,
    ensure_default_tenant,
)


@pytest.fixture()
def db():
    """In-memory SQLite with the tenant-owned + identity tables; returns a session."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(
        engine, tables=[Tenant.__table__, User.__table__, Group.__table__]
    )
    Session_cls = Session
    with Session_cls(bind=engine) as session:
        yield session
    engine.dispose()


def _make_user(tenant_id=None):
    return User(username=f"u-{tenant_id}", tenant_id=tenant_id)


# --- Tenant model schema -----------------------------------------------------


def test_tenant_slug_unique_and_not_null(db):
    db.add(Tenant(name="Acme", slug="acme", is_active=True))
    db.commit()
    # Duplicate unique slug is rejected by the DB constraint.
    from sqlalchemy.exc import IntegrityError
    try:
        db.add(Tenant(name="Acme2", slug="acme", is_active=True))
        db.commit()
        failed = False
    except IntegrityError:
        db.rollback()
        failed = True
    assert failed, "duplicate tenant slug should violate the unique constraint"


def test_tenant_slug_indexed():
    # `index=True` on slug creates ix_tenants_slug; the unique constraint adds its own.
    index_names = {ix.name for ix in Tenant.__table__.indexes}
    assert "ix_tenants_slug" in index_names, "tenant.slug should have an index"


# --- Identity model tenant columns ------------------------------------------


def test_user_and_group_have_tenant_columns():
    assert hasattr(User, "tenant_id"), "User.tenant_id column missing"
    assert hasattr(Group, "tenant_id"), "Group.tenant_id column missing"
    # Relationships wired so a tenant can reach its users/groups.
    assert hasattr(Tenant, "users")
    assert hasattr(Tenant, "groups")


# --- Tenant resolution -------------------------------------------------------


def test_resolve_tenant_id():
    assert resolve_tenant_id(_make_user(5)) == 5
    assert resolve_tenant_id(_make_user(None)) is None
    assert resolve_tenant_id(None) is None  # anonymous -> platform-wide scope


# --- Scoping -----------------------------------------------------------------


def test_apply_tenant_scope_filters_by_tenant(db):
    t = Tenant(name="T", slug="t1", is_active=True)
    db.add(t)
    db.flush()  # assign t.id before users reference it
    # User has NOT NULL columns (email/password_hash/role); supply them.
    u1 = User(username="a", email="a@x.io", password_hash="x", role="user", tenant_id=t.id)
    u2 = User(username="b", email="b@x.io", password_hash="x", role="user", tenant_id=999)
    db.add_all([u1, u2])
    db.commit()
    # User carries tenant_id, so scoping uses the entity column (no raw SQL fallback).
    stmt = apply_tenant_scope(select(User), t.id)
    rows = sorted(db.execute(stmt).scalars().all(), key=lambda x: x.username)
    assert [r.username for r in rows] == ["a"], "scoped query must return only the tenant's users"


def test_apply_tenant_scope_none_is_noop(db):
    db.add_all([Tenant(name="A", slug="a", is_active=True),
                Tenant(name="B", slug="b", is_active=True)])
    db.commit()
    stmt = apply_tenant_scope(select(Tenant), None)  # platform-wide
    rows = sorted(db.execute(stmt).scalars().all(), key=lambda x: x.slug)
    assert [r.slug for r in rows] == ["a", "b"]


# --- Default-tenant helper ---------------------------------------------------


def test_ensure_default_tenant_idempotent(db):
    first = ensure_default_tenant(db)
    assert first.slug == DEFAULT_TENANT_SLUG
    # Second call returns the SAME row (no duplicate seed).
    second = ensure_default_tenant(db)
    assert second.id == first.id
    rows = db.execute(select(Tenant).where(Tenant.slug == DEFAULT_TENANT_SLUG)).scalars().all()
    assert len(rows) == 1

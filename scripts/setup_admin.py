#!/usr/bin/env python3
"""
Setup / bootstrap-admin utility.

Usage:
    python scripts/setup_admin.py            Create the first admin (if missing)
    python scripts/setup_admin.py --show     Retrieve the persisted bootstrap password
    python scripts/setup_admin.py --reset    Regenerate + persist a new bootstrap password

Findings #7 fix: on first run the app generates a high-entropy random admin password
and logs it only *masked*. If that startup log is never retained, the operator has no
way to obtain the credentials (self-inflicted lock-out). To make the password
retrievable regardless of log retention, this script (and ``create_default_admin`` in
app/main.py) persist the plaintext bootstrap password encrypted-at-rest in
``system_settings.bootstrap_admin_password`` (Fernet, keyed off SECRET_KEY).

NOTE: passlib is intentionally NOT imported here. The app uses native `bcrypt`
(see app/services/auth_service.py) because bcrypt 4.x removed the low-level C API
passlib depends on ("(trapped) error reading bcrypt version"). Password hashing for
the admin account below is done by auth_service.create_user -> _hash_password
(native bcrypt), so the old `CryptContext` shim was dead code and is dropped.
(findings #10 — residual passlib reference removed)
"""
import argparse
import asyncio
import secrets
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

# Add backend to path
sys.path.insert(0, "backend")

from app.core.database import Base, engine  # noqa: E402
from app.models.auth import User  # noqa: E402
from app.models.system_settings import SystemSetting  # noqa: E402
from app.services.auth_service import auth_service  # noqa: E402
from app.api.system_settings import get_setting  # noqa: E402
from app.utils.secret_encryption import decrypt_secret  # noqa: E402

BOOTSTRAP_PASSWORD_KEY = "bootstrap_admin_password"


async def _get_bootstrap_password(db: AsyncSession) -> str | None:
    """Return the persisted plaintext bootstrap password, or None if not set."""
    token = await get_setting(db, BOOTSTRAP_PASSWORD_KEY, "")
    if not token:
        return None
    # decrypt_secret falls back to plaintext for legacy/cleartext values, so a value
    # written before encryption-at-rest (findings #34) still round-trips.
    plaintext = decrypt_secret(token)
    return plaintext or None


async def _create_admin(db: AsyncSession) -> str:
    """Create the first admin with a high-entropy random password and persist it."""
    # Ensure tables exist on the same DB we use below (idempotent). DDL needs a
    # Connection (create_all can't run against a Session), so run it on the session's
    # own connection inside an explicit transaction, then use `db` for data.
    async with db.begin():
        conn = await db.connection()
        await conn.run_sync(Base.metadata.create_all)

    bootstrap_password = secrets.token_urlsafe(18)  # ~128 bits of entropy
    admin_user = await auth_service.create_user(
        db=db,
        username="admin",
        email="admin@example.com",
        password=bootstrap_password,
        role="admin",
        full_name="Administrator",
    )
    # Persist the plaintext so it is retrievable even if the startup log is lost (#7).
    from app.api.system_settings import set_setting

    await set_setting(db, BOOTSTRAP_PASSWORD_KEY, bootstrap_password)
    return bootstrap_password


async def cmd_show(db: AsyncSession) -> int:
    """Print the persisted bootstrap password (findings #7)."""
    existing = (await db.execute(
        select(User).where(User.username == "admin")
    )).scalar_one_or_none()
    if not existing:
        print("No admin user exists yet. Run without --show to create one.")
        return 1
    pw = await _get_bootstrap_password(db)
    if pw is None:
        print(
            "No persisted bootstrap password found.\n"
            "  The admin was likely created before findings #7 was fixed, so its\n"
            "  password was never stored retrievably. Use --reset to set a new one:"
            "\n    python scripts/setup_admin.py --reset"
        )
        return 1
    print(f"Bootstrap admin password: {pw}")
    print("(Change it after first login via PUT /auth/users/{id}.)")
    return 0


async def cmd_reset(db: AsyncSession) -> int:
    """Regenerate + persist a new bootstrap password (findings #7)."""
    existing = (await db.execute(
        select(User).where(User.username == "admin")
    )).scalar_one_or_none()
    if not existing:
        pw = await _create_admin(db)
        print("✓ Admin user created!")
        print(f"  Username: admin")
        print(f"  Password: {pw}")
        print(f"  Email: admin@example.com")
        print("\n⚠️  IMPORTANT: Change the password after first login!")
        return 0

    from app.api.system_settings import set_setting

    new_password = secrets.token_urlsafe(18)
    await set_setting(db, BOOTSTRAP_PASSWORD_KEY, new_password)
    print("✓ Bootstrap password reset.")
    print(f"  Username: admin")
    print(f"  New password: {new_password}")
    print(f"  Email: admin@example.com")
    print("\n⚠️  IMPORTANT: Change the password after first login!")
    return 0


async def cmd_create(db: AsyncSession) -> int:
    """Create the first admin if none exists (default behavior)."""
    existing = (await db.execute(
        select(User).where(User.username == "admin")
    )).scalar_one_or_none()
    if existing:
        print("Admin user already exists!")
        print("Retrieve its password with: python scripts/setup_admin.py --show")
        return 0
    pw = await _create_admin(db)
    print(f"✓ Admin user created!")
    print(f"  Username: admin")
    print(f"  Password: {pw}")
    print(f"  Email: admin@example.com")
    print(
        "\nIf this output is not retained, retrieve the password later with:\n"
        "    python scripts/setup_admin.py --show"
    )
    print("\n⚠️  IMPORTANT: Change the password after first login!")
    return 0


async def setup_admin() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap/reset the admin user")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--show", action="store_true", help="Retrieve the persisted bootstrap password")
    group.add_argument("--reset", action="store_true", help="Regenerate + persist a new bootstrap password")
    args = parser.parse_args()

    async with AsyncSession(engine) as db:
        if args.show:
            return await cmd_show(db)
        if args.reset:
            return await cmd_reset(db)
        return await cmd_create(db)


if __name__ == "__main__":
    sys.exit(asyncio.run(setup_admin()))

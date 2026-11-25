"""
Regression test for findings #10 (residual passlib reference in setup_admin.py).

The script previously did `from passlib.context import CryptContext` and built a
`pwd_context`. Because passlib is not in requirements.txt — and passlib + bcrypt
4.x raises "(trapped) error reading bcrypt version" — the script failed at import.
The fix dropped the passlib import and routes password hashing through the app's
native-bcrypt helper (`auth_service.create_user` -> `_hash_password`).

This test proves the fix by blocking `passlib` in sys.modules and loading
setup_admin.py fresh: if it still referenced passlib, the import would raise
ImportError. It also asserts the module exposes setup_admin and relies on the
app's native-bcrypt auth_service rather than a CryptContext shim.
"""
import importlib.util
import sys
import pathlib

import pytest

# Test lives at backend/tests/; the script is at repo-root/scripts/.
REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
SCRIPT = REPO_ROOT / "scripts" / "setup_admin.py"


class _BlockedPasslib:
    """Stand-in for the `passlib` package that fails on any attribute access."""

    def __getattr__(self, name):
        raise ImportError("passlib is blocked for findings #10 test")


def _load_setup_admin():
    spec = importlib.util.spec_from_file_location("setup_admin_probe", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_setup_admin_imports_without_passlib():
    real = sys.modules.get("passlib")
    sys.modules["passlib"] = _BlockedPasslib()
    try:
        mod = _load_setup_admin()
    except ImportError as e:  # would happen if the script still imported passlib
        raise AssertionError(f"setup_admin.py still requires passlib: {e}") from e
    finally:
        if real is not None:
            sys.modules["passlib"] = real
        else:
            sys.modules.pop("passlib", None)

    # The script exposes its entry point and uses the app's native-bcrypt helper.
    assert hasattr(mod, "setup_admin")
    # It must rely on auth_service (native bcrypt), not a passlib CryptContext shim.
    assert hasattr(mod, "auth_service")
    assert not hasattr(mod, "pwd_context")

"""
Encryption-at-rest helpers for sensitive ``system_settings`` values (findings #34).

Credentials such as SMTP/IMAP/LDAP passwords are stored *encrypted* in the
``system_settings`` table using Fernet (authenticated AES-128-CBC + HMAC-SHA256).
The encryption key is derived from the process ``SECRET_KEY``, which lives in the
environment — so secrets are never persisted in cleartext in the application
database, yet decryption works across restarts as long as ``SECRET_KEY`` is
unchanged. (If the key changes, previously stored secrets must be re-saved.)

The keys below are the only ``system_settings`` rows that carry a secret; every
write through ``set_setting`` encrypts them, and the internal read sites decrypt
them back to plaintext for runtime use.
"""
import base64
import hashlib
from typing import Optional

from cryptography.fernet import Fernet

# system_settings keys whose stored value is a secret and must be encrypted at rest.
SECRET_SETTING_KEYS = frozenset({
    "smtp_password",
    "imap_password",
    "ldap_bind_password",
    # Bootstrap admin password created on first run (findings #7). Stored encrypted
    # at rest so the retrievable fallback credential never sits in cleartext in the
    # database; read back via decrypt_secret(get_setting(db, "bootstrap_admin_password")).
    "bootstrap_admin_password",
})


def _derive_key(secret_key: str) -> bytes:
    """Derive a Fernet-compatible key (urlsafe-base64 of 32 raw bytes)."""
    digest = hashlib.sha256(secret_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    # Lazy import to avoid any import-order/circular-import issues at module load.
    from app.core.config import settings
    return Fernet(_derive_key(settings.secret_key))


def encrypt_secret(plaintext: Optional[str]) -> str:
    """Encrypt a plaintext secret, returning a urlsafe-base64 Fernet token.

    ``None``/empty input returns an empty string (nothing to store).
    """
    if not plaintext:
        return ""
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: Optional[str]) -> str:
    """Decrypt a Fernet token back to plaintext.

    Returns ``""`` for empty/None input. On decryption failure (e.g. legacy
    plaintext stored before encryption-at-rest, or a ``SECRET_KEY`` rotation that
    invalidated stored tokens) the input is returned unchanged rather than raising,
    so startup never crashes and pre-encryption plaintext passes through intact.
    """
    if not token:
        return ""
    try:
        return _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception:
        return token
